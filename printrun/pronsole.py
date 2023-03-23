# This file is part of the Printrun suite.
#
# Printrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Printrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

import cmd
import glob
import os
import platform
import time
import threading
import sys
import shutil
import subprocess
import codecs
import argparse
import logging
import traceback
import re

from appdirs import user_cache_dir, user_config_dir, user_data_dir
from serial import SerialException

from . import printcore
from .utils import run_command, get_command_output, \
    format_time, format_duration, RemainingTimeEstimator, \
    get_home_pos, parse_build_dimensions, parse_temperature_report, \
    setup_logging

from .settings import Settings, BuildDimensionsSetting
from .power import powerset_print_start, powerset_print_stop
from printrun import gcoder
from .rpc import ProntRPC

if os.name == "nt":
    try:
        import winreg
    except:
        pass
READLINE = True
try:
    import readline
    try:
        readline.rl.mode.show_all_if_ambiguous = "on"  # config pyreadline on windows
    except:
        pass
except:
    READLINE = False  # neither readline module is available

tempreading_exp = re.compile('\\bT\d*:')

REPORT_NONE = 0
REPORT_POS = 1
REPORT_TEMP = 2
REPORT_MANUAL = 4
DEG = "\N{DEGREE SIGN}"

class Status:

    def __init__(self):
        self.extruder_temp = 0
        self.extruder_temp_target = 0
        self.bed_temp = 0
        self.bed_temp_target = 0
        self.print_job = None
        self.print_job_progress = 1.0

    @property
    def bed_enabled(self):
        return self.bed_temp != 0

    @property
    def extruder_enabled(self):
        return self.extruder_temp != 0

class RGSGCoder():
    """Bare alternative to gcoder.LightGCode which does not preload all lines in memory,
but still allows run_gcode_script (hence the RGS) to be processed by do_print (checksum,threading,ok waiting)"""
    def __init__(self, line):
        self.lines = True
        self.filament_length = 0.
        self.filament_length_multi = [0]
        self.proc = run_command(line, {"$s": 'str(self.filename)'}, stdout = subprocess.PIPE, universal_newlines = True)
        lr = gcoder.Layer([])
        lr.duration = 0.
        self.all_layers = [lr]
        self.read() #empty layer causes division by zero during progress calculation
    def read(self):
        ln = self.proc.stdout.readline()
        if not ln:
            self.proc.stdout.close()
            return None
        ln = ln.strip()
        if not ln:
            return None
        pyLn = gcoder.PyLightLine(ln)
        self.all_layers[0].append(pyLn)
        return pyLn
    def has_index(self, i):
        while i >= len(self.all_layers[0]) and not self.proc.stdout.closed:
            self.read()
        return i < len(self.all_layers[0])
    def __len__(self):
        return len(self.all_layers[0])
    def idxs(self, i):
        return 0, i #layer, line

class pronsole(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        if not READLINE:
            self.completekey = None
        self.status = Status()
        self.dynamic_temp = False
        self.compute_eta = None
        self.statuscheck = False
        self.status_thread = None
        self.p = printcore.printcore()
        self.p.recvcb = self.recvcb
        self.p.startcb = self.startcb
        self.p.endcb = self.endcb
        self.p.layerchangecb = self.layer_change_cb
        self.p.process_host_command = self.process_host_command
        self.recvlisteners = []
        self.in_macro = False
        self.p.onlinecb = self.online
        self.p.errorcb = self.logError
        self.fgcode = None
        self.filename = None
        self.rpc_server = None
        self.curlayer = 0
        self.sdlisting = 0
        self.sdlisting_echo = 0
        self.sdfiles = []
        self.paused = False
        self.sdprinting = 0
        self.uploading = 0  # Unused, just for pronterface generalization
        self.percentdone = 0
        self.posreport = ""
        self.userm114 = 0
        self.userm105 = 0
        self.m105_waitcycles = 0
        self.macros = {}
        self.rc_loaded = False
        self.processing_rc = False
        self.processing_args = False
        self.settings = Settings(self)
        self.settings._add(BuildDimensionsSetting("build_dimensions", "200x200x100+0+0+0+0+0+0", "Build dimensions", "Dimensions of Build Platform\n & optional offset of origin\n & optional switch position\n\nExamples:\n   XXXxYYY\n   XXX,YYY,ZZZ\n   XXXxYYYxZZZ+OffX+OffY+OffZ\nXXXxYYYxZZZ+OffX+OffY+OffZ+HomeX+HomeY+HomeZ", "Printer"), self.update_build_dimensions)
        self.settings._port_list = self.scanserial
        self.update_build_dimensions(None, self.settings.build_dimensions)
        self.update_tcp_streaming_mode(None, self.settings.tcp_streaming_mode)
        self.monitoring = 0
        self.starttime = 0
        self.extra_print_time = 0
        self.silent = False
        self.commandprefixes = 'MGTD$'
        self.promptstrs = {"offline": "%(bold)soffline>%(normal)s ",
                           "fallback": "%(bold)s%(red)s%(port)s%(white)s PC>%(normal)s ",
                           "macro": "%(bold)s..>%(normal)s ",
                           "online": "%(bold)s%(green)s%(port)s%(white)s %(extruder_temp_fancy)s%(progress_fancy)s>%(normal)s "}
        self.current_tool = 0   # Keep track of the extruder being used
        self.cache_dir = os.path.join(user_cache_dir("Printrun"))
        self.history_file = os.path.join(self.cache_dir,"history")
        self.config_dir = os.path.join(user_config_dir("Printrun"))
        self.data_dir = os.path.join(user_data_dir("Printrun"))
        self.lineignorepattern=re.compile("ok ?\d*$|.*busy: ?processing|.*busy: ?heating|.*Active Extruder: ?\d*$")

    #  --------------------------------------------------------------
    #  General console handling
    #  --------------------------------------------------------------

    def postloop(self):
        self.p.disconnect()
        cmd.Cmd.postloop(self)

    def preloop(self):
        self.log("Welcome to the printer console! Type \"help\" for a list of available commands.")
        self.prompt = self.promptf()
        cmd.Cmd.preloop(self)

    # We replace this function, defined in cmd.py .
    # It's default behavior with regards to Ctr-C
    # and Ctr-D doesn't make much sense...
    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        """

        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                import readline
                self.old_completer = readline.get_completer()
                readline.set_completer(self.complete)
                readline.parse_and_bind(self.completekey + ": complete")
                history = (self.history_file)
                if not os.path.exists(history):
                    if not os.path.exists(self.cache_dir):
                        os.makedirs(self.cache_dir)
                    history = os.path.join(self.cache_dir, "history")
                if os.path.exists(history):
                    readline.read_history_file(history)
            except ImportError:
                pass
        try:
            if intro is not None:
                self.intro = intro
            if self.intro:
                self.stdout.write(str(self.intro) + "\n")
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.prompt)
                        except EOFError:
                            self.log("")
                            self.do_exit("")
                        except KeyboardInterrupt:
                            self.log("")
                            line = ""
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not len(line):
                            line = ""
                        else:
                            line = line.rstrip('\r\n')
                line = self.precmd(line)
                stop = self.onecmd(line)
                stop = self.postcmd(stop, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    import readline
                    readline.set_completer(self.old_completer)
                    readline.write_history_file(self.history_file)
                except ImportError:
                    pass

    def confirm(self):
        y_or_n = input("y/n: ")
        if y_or_n == "y":
            return True
        elif y_or_n != "n":
            return self.confirm()
        return False

    def log(self, *msg):
        msg = "".join(str(i) for i in msg)
        logging.info(msg)

    def logError(self, *msg):
        msg = "".join(str(i) for i in msg)
        logging.error(msg)
        if not self.settings.error_command:
            return
        output = get_command_output(self.settings.error_command, {"$m": msg})
        if output:
            self.log("Error command output:")
            self.log(output.rstrip())

    def promptf(self):
        """A function to generate prompts so that we can do dynamic prompts. """
        if self.in_macro:
            promptstr = self.promptstrs["macro"]
        elif not self.p.online:
            promptstr = self.promptstrs["offline"]
        elif self.status.extruder_enabled:
            promptstr = self.promptstrs["online"]
        else:
            promptstr = self.promptstrs["fallback"]
        if "%" not in promptstr:
            return promptstr
        else:
            specials = {}
            specials["extruder_temp"] = str(int(self.status.extruder_temp))
            specials["extruder_temp_target"] = str(int(self.status.extruder_temp_target))
            # port: /dev/tty* | netaddress:port
            specials["port"] = self.settings.port.replace('/dev/', '')
            if self.status.extruder_temp_target == 0:
                specials["extruder_temp_fancy"] = str(int(self.status.extruder_temp)) + DEG
            else:
                specials["extruder_temp_fancy"] = "%s%s/%s%s" % (str(int(self.status.extruder_temp)), DEG, str(int(self.status.extruder_temp_target)), DEG)
            if self.p.printing:
                progress = int(1000 * float(self.p.queueindex) / len(self.p.mainqueue)) / 10
            elif self.sdprinting:
                progress = self.percentdone
            else:
                progress = 0.0
            specials["progress"] = str(progress)
            if self.p.printing or self.sdprinting:
                specials["progress_fancy"] = " " + str(progress) + "%"
            else:
                specials["progress_fancy"] = ""
            specials["red"] = "\033[31m"
            specials["green"] = "\033[32m"
            specials["white"] = "\033[37m"
            specials["bold"] = "\033[01m"
            specials["normal"] = "\033[00m"
            return promptstr % specials

    def postcmd(self, stop, line):
        """ A hook we override to generate prompts after
            each command is executed, for the next prompt.
            We also use it to send M105 commands so that
            temp info gets updated for the prompt."""
        if self.p.online and self.dynamic_temp:
            self.p.send_now("M105")
        self.prompt = self.promptf()
        return stop

    def kill(self):
        self.statuscheck = False
        if self.status_thread:
            self.status_thread.join()
            self.status_thread = None
        if self.rpc_server is not None:
            self.rpc_server.shutdown()

    def write_prompt(self):
        sys.stdout.write(self.promptf())
        sys.stdout.flush()

    def help_help(self, l = ""):
        self.do_help("")

    def do_gcodes(self, l = ""):
        self.help_gcodes()

    def help_gcodes(self):
        self.log("Gcodes are passed through to the printer as they are")

    def precmd(self, line):
        if line.upper().startswith("M114"):
            self.userm114 += 1
        elif line.upper().startswith("M105"):
            self.userm105 += 1
        return line

    def help_shell(self):
        self.log("Executes a python command. Example:")
        self.log("! os.listdir('.')")

    def do_shell(self, l):
        exec(l)

    def emptyline(self):
        """Called when an empty line is entered - do not remove"""
        pass

    def default(self, l):
        if l[0].upper() in self.commandprefixes.upper():
            if self.p and self.p.online:
                if not self.p.loud:
                    self.log("SENDING:" + l.upper())
                self.p.send_now(l.upper())
            else:
                self.logError("Printer is not online.")
            return
        elif l[0] == "@":
            if self.p and self.p.online:
                if not self.p.loud:
                    self.log("SENDING:" + l[1:])
                self.p.send_now(l[1:])
            else:
                self.logError("Printer is not online.")
            return
        else:
            cmd.Cmd.default(self, l)

    def do_exit(self, l):
        if self.status.extruder_temp_target != 0:
            self.log("Setting extruder temp to 0")
        self.p.send_now("M104 S0.0")
        if self.status.bed_enabled:
            if self.status.bed_temp_target != 0:
                self.log("Setting bed temp to 0")
            self.p.send_now("M140 S0.0")
        self.log("Disconnecting from printer...")
        if self.p.printing and l != "force":
            self.log("Are you sure you want to exit while printing?\n\
(this will terminate the print).")
            if not self.confirm():
                return
        self.log("Exiting program. Goodbye!")
        self.p.disconnect()
        self.kill()
        sys.exit()

    def help_exit(self):
        self.log("Disconnects from the printer and exits the program.")

    # --------------------------------------------------------------
    # Macro handling
    # --------------------------------------------------------------

    def complete_macro(self, text, line, begidx, endidx):
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in self.macros.keys() if i.startswith(text)]
        elif len(line.split()) == 3 or (len(line.split()) == 2 and line[-1] == " "):
            return [i for i in ["/D", "/S"] + self.completenames(text) if i.startswith(text)]
        else:
            return []

    def hook_macro(self, l):
        l = l.rstrip()
        ls = l.lstrip()
        ws = l[:len(l) - len(ls)]  # just leading whitespace
        if len(ws) == 0:
            self.end_macro()
            # pass the unprocessed line to regular command processor to not require empty line in .pronsolerc
            return self.onecmd(l)
        self.cur_macro_def += l + "\n"

    def end_macro(self):
        if "onecmd" in self.__dict__: del self.onecmd  # remove override
        self.in_macro = False
        self.prompt = self.promptf()
        if self.cur_macro_def != "":
            self.macros[self.cur_macro_name] = self.cur_macro_def
            macro = self.compile_macro(self.cur_macro_name, self.cur_macro_def)
            setattr(self.__class__, "do_" + self.cur_macro_name, lambda self, largs, macro = macro: macro(self, *largs.split()))
            setattr(self.__class__, "help_" + self.cur_macro_name, lambda self, macro_name = self.cur_macro_name: self.subhelp_macro(macro_name))
            if not self.processing_rc:
                self.log("Macro '" + self.cur_macro_name + "' defined")
                # save it
                if not self.processing_args:
                    macro_key = "macro " + self.cur_macro_name
                    macro_def = macro_key
                    if "\n" in self.cur_macro_def:
                        macro_def += "\n"
                    else:
                        macro_def += " "
                    macro_def += self.cur_macro_def
                    self.save_in_rc(macro_key, macro_def)
        else:
            self.logError("Empty macro - cancelled")
        del self.cur_macro_name, self.cur_macro_def

    def compile_macro_line(self, line):
        line = line.rstrip()
        ls = line.lstrip()
        ws = line[:len(line) - len(ls)]  # just leading whitespace
        if ls == "" or ls.startswith('#'): return ""  # no code
        if ls.startswith('!'):
            return ws + ls[1:] + "\n"  # python mode
        else:
            ls = ls.replace('"', '\\"')  # need to escape double quotes
            ret = ws + 'self.precmd("' + ls + '".format(*arg))\n'  # parametric command mode
            return ret + ws + 'self.onecmd("' + ls + '".format(*arg))\n'

    def compile_macro(self, macro_name, macro_def):
        if macro_def.strip() == "":
            self.logError("Empty macro - cancelled")
            return
        macro = None
        namespace={}
        pycode = "def macro(self,*arg):\n"
        if "\n" not in macro_def.strip():
            pycode += self.compile_macro_line("  " + macro_def.strip())
        else:
            lines = macro_def.split("\n")
            for l in lines:
                pycode += self.compile_macro_line(l)
        exec(pycode,namespace)
        try:
            macro=namespace['macro']
        except:
            pass
        return macro

    def start_macro(self, macro_name, prev_definition = "", suppress_instructions = False):
        if not self.processing_rc and not suppress_instructions:
            self.logError("Enter macro using indented lines, end with empty line")
        self.cur_macro_name = macro_name
        self.cur_macro_def = ""
        self.onecmd = self.hook_macro  # override onecmd temporarily
        self.in_macro = False
        self.prompt = self.promptf()

    def delete_macro(self, macro_name):
        if macro_name in self.macros.keys():
            delattr(self.__class__, "do_" + macro_name)
            del self.macros[macro_name]
            self.log("Macro '" + macro_name + "' removed")
            if not self.processing_rc and not self.processing_args:
                self.save_in_rc("macro " + macro_name, "")
        else:
            self.logError("Macro '" + macro_name + "' is not defined")

    def do_macro(self, args):
        if args.strip() == "":
            self.print_topics("User-defined macros", [str(k) for k in self.macros.keys()], 15, 80)
            return
        arglist = args.split(None, 1)
        macro_name = arglist[0]
        if macro_name not in self.macros and hasattr(self.__class__, "do_" + macro_name):
            self.logError("Name '" + macro_name + "' is being used by built-in command")
            return
        if len(arglist) == 2:
            macro_def = arglist[1]
            if macro_def.lower() == "/d":
                self.delete_macro(macro_name)
                return
            if macro_def.lower() == "/s":
                self.subhelp_macro(macro_name)
                return
            self.cur_macro_def = macro_def
            self.cur_macro_name = macro_name
            self.end_macro()
            return
        if macro_name in self.macros:
            self.start_macro(macro_name, self.macros[macro_name])
        else:
            self.start_macro(macro_name)

    def help_macro(self):
        self.log("Define single-line macro: macro <name> <definition>")
        self.log("Define multi-line macro:  macro <name>")
        self.log("Enter macro definition in indented lines. Use {0} .. {N} to substitute macro arguments")
        self.log("Enter python code, prefixed with !  Use arg[0] .. arg[N] to substitute macro arguments")
        self.log("Delete macro:             macro <name> /d")
        self.log("Show macro definition:    macro <name> /s")
        self.log("'macro' without arguments displays list of defined macros")

    def subhelp_macro(self, macro_name):
        if macro_name in self.macros.keys():
            macro_def = self.macros[macro_name]
            if "\n" in macro_def:
                self.log("Macro '" + macro_name + "' defined as:")
                self.log(self.macros[macro_name] + "----------------")
            else:
                self.log("Macro '" + macro_name + "' defined as: '" + macro_def + "'")
        else:
            self.logError("Macro '" + macro_name + "' is not defined")

    # --------------------------------------------------------------
    # Configuration handling
    # --------------------------------------------------------------

    def set(self, var, str):
        try:
            t = type(getattr(self.settings, var))
            value = self.settings._set(var, str)
            if not self.processing_rc and not self.processing_args:
                self.save_in_rc("set " + var, "set %s %s" % (var, value))
        except AttributeError:
            logging.debug("Unknown variable '%s'" % var)
        except ValueError as ve:
            if hasattr(ve, "from_validator"):
                self.logError("Bad value %s for variable '%s': %s" % (str, var, ve.args[0]))
            else:
                self.logError("Bad value for variable '%s', expecting %s (%s)" % (var, repr(t)[1:-1], ve.args[0]))

    def do_set(self, argl):
        args = argl.split(None, 1)
        if len(args) < 1:
            for k in [kk for kk in dir(self.settings) if not kk.startswith("_")]:
                self.log("%s = %s" % (k, str(getattr(self.settings, k))))
            return
        if len(args) < 2:
            # Try getting the default value of the setting to check whether it
            # actually exists
            try:
                getattr(self.settings, args[0])
            except AttributeError:
                logging.warning("Unknown variable '%s'" % args[0])
            return
        self.set(args[0], args[1])

    def help_set(self):
        self.log("Set variable:   set <variable> <value>")
        self.log("Show variable:  set <variable>")
        self.log("'set' without arguments displays all variables")

    def complete_set(self, text, line, begidx, endidx):
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in dir(self.settings) if not i.startswith("_") and i.startswith(text)]
        elif len(line.split()) == 3 or (len(line.split()) == 2 and line[-1] == " "):
            return [i for i in self.settings._tabcomplete(line.split()[1]) if i.startswith(text)]
        else:
            return []

    def load_rc(self, rc_filename):
        self.processing_rc = True
        try:
            rc = codecs.open(rc_filename, "r", "utf-8")
            self.rc_filename = os.path.abspath(rc_filename)
            for rc_cmd in rc:
                if not rc_cmd.lstrip().startswith("#"):
                    logging.debug(rc_cmd.rstrip())
                    self.onecmd(rc_cmd)
            rc.close()
            if hasattr(self, "cur_macro_def"):
                self.end_macro()
            self.rc_loaded = True
        finally:
            self.processing_rc = False

    def load_default_rc(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        config_name = ('pronsolerc')

        config = os.path.join(self.config_dir, config_name)
        logging.info('Loading config file ' + config)

        # Load the default configuration file
        try:
            self.load_rc(config)
        except FileNotFoundError:
            # Make sure the filename is initialized,
            # and create the file if it doesn't exist
            self.rc_filename = config
            open(self.rc_filename, 'a').close()

    def save_in_rc(self, key, definition):
        """
        Saves or updates macro or other definitions in .pronsolerc
        key is prefix that determines what is being defined/updated (e.g. 'macro foo')
        definition is the full definition (that is written to file). (e.g. 'macro foo move x 10')
        Set key as empty string to just add (and not overwrite)
        Set definition as empty string to remove it from .pronsolerc
        To delete line from .pronsolerc, set key as the line contents, and definition as empty string
        Only first definition with given key is overwritten.
        Updates are made in the same file position.
        Additions are made to the end of the file.
        """
        rci, rco = None, None
        if definition != "" and not definition.endswith("\n"):
            definition += "\n"
        try:
            written = False
            if os.path.exists(self.rc_filename):
                if not os.path.exists(self.cache_dir):
                    os.makedirs(self.cache_dir)
                configcache = os.path.join(self.cache_dir, os.path.basename(self.rc_filename))
                configcachebak = configcache + "~bak"
                configcachenew = configcache + "~new"
                shutil.copy(self.rc_filename, configcachebak)
                rci = codecs.open(configcachebak, "r", "utf-8")
            rco = codecs.open(configcachenew, "w", "utf-8")
            if rci is not None:
                overwriting = False
                for rc_cmd in rci:
                    l = rc_cmd.rstrip()
                    ls = l.lstrip()
                    ws = l[:len(l) - len(ls)]  # just leading whitespace
                    if overwriting and len(ws) == 0:
                        overwriting = False
                    if not written and key != "" and rc_cmd.startswith(key) and (rc_cmd + "\n")[len(key)].isspace():
                        overwriting = True
                        written = True
                        rco.write(definition)
                    if not overwriting:
                        rco.write(rc_cmd)
                        if not rc_cmd.endswith("\n"): rco.write("\n")
            if not written:
                rco.write(definition)
            if rci is not None:
                rci.close()
            rco.close()
            shutil.move(configcachenew, self.rc_filename)
            # if definition != "":
            #    self.log("Saved '"+key+"' to '"+self.rc_filename+"'")
            # else:
            #    self.log("Removed '"+key+"' from '"+self.rc_filename+"'")
        except Exception as e:
            self.logError("Saving failed for ", key + ":", str(e))
        finally:
            del rci, rco

    #  --------------------------------------------------------------
    #  Configuration update callbacks
    #  --------------------------------------------------------------

    def update_build_dimensions(self, param, value):
        self.build_dimensions_list = parse_build_dimensions(value)
        self.p.analyzer.home_pos = get_home_pos(self.build_dimensions_list)

    def update_tcp_streaming_mode(self, param, value):
        self.p.tcp_streaming_mode = self.settings.tcp_streaming_mode

    def update_rpc_server(self, param, value):
        if value:
            if self.rpc_server is None:
                self.rpc_server = ProntRPC(self)
        else:
            if self.rpc_server is not None:
                self.rpc_server.shutdown()
                self.rpc_server = None

    #  --------------------------------------------------------------
    #  Command line options handling
    #  --------------------------------------------------------------

    def add_cmdline_arguments(self, parser):
        parser.add_argument('-v', '--verbose', help = "increase verbosity", action = "store_true")
        parser.add_argument('-c', '--conf', '--config', help = "load this file on startup instead of .pronsolerc ; you may chain config files, if so settings auto-save will use the last specified file", action = "append", default = [])
        parser.add_argument('-e', '--execute', help = "executes command after configuration/.pronsolerc is loaded ; macros/settings from these commands are not autosaved", action = "append", default = [])
        parser.add_argument('filename', nargs='?', help = "file to load")

    def process_cmdline_arguments(self, args):
        if args.verbose:
            logger = logging.getLogger()
            logger.setLevel(logging.DEBUG)
        for config in args.conf:
            try:
                self.load_rc(config)
            except EnvironmentError as err:
                print(("ERROR: Unable to load configuration file: %s" %
                       str(err)[10:]))
                sys.exit(1)
        if not self.rc_loaded:
            self.load_default_rc()
        self.processing_args = True
        for command in args.execute:
            self.onecmd(command)
        self.processing_args = False
        self.update_rpc_server(None, self.settings.rpc_server)
        if args.filename:
            self.cmdline_filename_callback(args.filename)

    def cmdline_filename_callback(self, filename):
        self.do_load(filename)

    def parse_cmdline(self, args):
        parser = argparse.ArgumentParser(description = 'Printrun 3D printer interface')
        self.add_cmdline_arguments(parser)
        args = [arg for arg in args if not arg.startswith("-psn")]
        args = parser.parse_args(args = args)
        self.process_cmdline_arguments(args)
        setup_logging(sys.stdout, self.settings.log_path, True)

    #  --------------------------------------------------------------
    #  Printer connection handling
    #  --------------------------------------------------------------

    def connect_to_printer(self, port, baud, dtr):
        try:
            self.p.connect(port, baud, dtr)
        except SerialException as e:
            # Currently, there is no errno, but it should be there in the future
            if e.errno == 2:
                self.logError("Error: You are trying to connect to a non-existing port.")
            elif e.errno == 8:
                self.logError("Error: You don't have permission to open %s." % port)
                self.logError("You might need to add yourself to the dialout group.")
            else:
                self.logError(traceback.format_exc())
            # Kill the scope anyway
            return False
        except OSError as e:
            if e.errno == 2:
                self.logError("Error: You are trying to connect to a non-existing port.")
            else:
                self.logError(traceback.format_exc())
            return False
        self.statuscheck = True
        self.status_thread = threading.Thread(target = self.statuschecker,
                                              name = 'status thread')
        self.status_thread.start()
        return True

    def do_connect(self, l):
        a = l.split()
        p = self.scanserial()
        port = self.settings.port
        if (port == "" or port not in p) and len(p) > 0:
            port = p[0]
        baud = self.settings.baudrate or 115200
        if len(a) > 0:
            port = a[0]
        if len(a) > 1:
            try:
                baud = int(a[1])
            except:
                self.log("Bad baud value '" + a[1] + "' ignored")
        if len(p) == 0 and not port:
            self.log("No serial ports detected - please specify a port")
            return
        if len(a) == 0:
            self.log("No port specified - connecting to %s at %dbps" % (port, baud))
        if port != self.settings.port:
            self.settings.port = port
            self.save_in_rc("set port", "set port %s" % port)
        if baud != self.settings.baudrate:
            self.settings.baudrate = baud
            self.save_in_rc("set baudrate", "set baudrate %d" % baud)
        self.connect_to_printer(port, baud, self.settings.dtr)

    def help_connect(self):
        self.log("Connect to printer")
        self.log("connect <port> <baudrate>")
        self.log("If port and baudrate are not specified, connects to first detected port at 115200bps")
        ports = self.scanserial()
        if ports:
            self.log("Available ports: ", " ".join(ports))
        else:
            self.log("No serial ports were automatically found.")

    def complete_connect(self, text, line, begidx, endidx):
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in self.scanserial() if i.startswith(text)]
        elif len(line.split()) == 3 or (len(line.split()) == 2 and line[-1] == " "):
            return [i for i in ["2400", "9600", "19200", "38400", "57600", "115200"] if i.startswith(text)]
        else:
            return []

    def scanserial(self):
        """scan for available ports. return a list of device names."""
        baselist = []
        if os.name == "nt":
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "HARDWARE\\DEVICEMAP\\SERIALCOMM")
                i = 0
                while(1):
                    baselist += [winreg.EnumValue(key, i)[1]]
                    i += 1
            except:
                pass

        for g in ['/dev/ttyUSB*', '/dev/ttyACM*', "/dev/tty.*", "/dev/cu.*", "/dev/rfcomm*"]:
            baselist += glob.glob(g)
        if(sys.platform!="win32" and self.settings.devicepath):
            baselist += glob.glob(self.settings.devicepath)
        return [p for p in baselist if self._bluetoothSerialFilter(p)]

    def _bluetoothSerialFilter(self, serial):
        return not ("Bluetooth" in serial or "FireFly" in serial)

    def online(self):
        self.log("\rPrinter is now online")
        self.write_prompt()

    def do_disconnect(self, l):
        self.p.disconnect()

    def help_disconnect(self):
        self.log("Disconnects from the printer")

    def do_block_until_online(self, l):
        while not self.p.online:
            time.sleep(0.1)

    def help_block_until_online(self, l):
        self.log("Blocks until printer is online")
        self.log("Warning: if something goes wrong, this can block pronsole forever")

    #  --------------------------------------------------------------
    #  Printer status monitoring
    #  --------------------------------------------------------------

    def statuschecker_inner(self, do_monitoring = True):
        if self.p.online:
            if self.p.writefailures >= 4:
                self.logError("Disconnecting after 4 failed writes.")
                self.status_thread = None
                self.p.disconnect()
                return
            if do_monitoring:
                if self.sdprinting and not self.paused:
                    self.p.send_now("M27")
                if self.m105_waitcycles % 10 == 0:
                    self.p.send_now("M105")
                self.m105_waitcycles += 1
        cur_time = time.time()
        wait_time = 0
        while time.time() < cur_time + self.monitor_interval - 0.25:
            if not self.statuscheck:
                break
            time.sleep(0.25)
            # Safeguard: if system time changes and goes back in the past,
            # we could get stuck almost forever
            wait_time += 0.25
            if wait_time > self.monitor_interval - 0.25:
                break
        # Always sleep at least a bit, if something goes wrong with the
        # system time we'll avoid freezing the whole app this way
        time.sleep(0.25)

    def statuschecker(self):
        while self.statuscheck:
            self.statuschecker_inner()

    #  --------------------------------------------------------------
    #  File loading handling
    #  --------------------------------------------------------------

    def do_load(self, filename):
        self._do_load(filename)

    def _do_load(self, filename):
        if not filename:
            self.logError("No file name given.")
            return
        self.log("Loading file: %s" % filename)
        if not os.path.exists(filename):
            self.logError("File not found!")
            return
        self.load_gcode(filename)
        self.log("Loaded %s, %d lines." % (filename, len(self.fgcode)))
        self.log("Estimated duration: %d layers, %s" % self.fgcode.estimate_duration())

    def load_gcode(self, filename, layer_callback = None, gcode = None):
        if gcode is None:
            self.fgcode = gcoder.LightGCode(deferred = True)
        else:
            self.fgcode = gcode
        self.fgcode.prepare(open(filename, "r", encoding="utf-8"),
                            get_home_pos(self.build_dimensions_list),
                            layer_callback = layer_callback)
        self.fgcode.estimate_duration()
        self.filename = filename

    def complete_load(self, text, line, begidx, endidx):
        s = line.split()
        if len(s) > 2:
            return []
        if (len(s) == 1 and line[-1] == " ") or (len(s) == 2 and line[-1] != " "):
            if len(s) > 1:
                return [i[len(s[1]) - len(text):] for i in glob.glob(s[1] + "*/") + glob.glob(s[1] + "*.g*")]
            else:
                return glob.glob("*/") + glob.glob("*.g*")

    def help_load(self):
        self.log("Loads a gcode file (with tab-completion)")

    def do_slice(self, l):
        l = l.split()
        if len(l) == 0:
            self.logError("No file name given.")
            return
        settings = 0
        if l[0] == "set":
            settings = 1
        else:
            self.log("Slicing file: %s" % l[0])
            if not(os.path.exists(l[0])):
                self.logError("File not found!")
                return
        try:
            if settings:
                command = self.settings.slicecommandpath+self.settings.sliceoptscommand
                self.log("Entering slicer settings: %s" % command)
                run_command(command, blocking = True)
            else:
                command = self.settings.slicecommandpath+self.settings.slicecommand
                stl_name = l[0]
                gcode_name = stl_name.replace(".stl", "_export.gcode").replace(".STL", "_export.gcode")
                run_command(command,
                            {"$s": stl_name,
                             "$o": gcode_name},
                            blocking = True)
                self.log("Loading sliced file.")
                self.do_load(l[0].replace(".stl", "_export.gcode"))
        except Exception as e:
            self.logError("Slicing failed: %s" % e)

    def complete_slice(self, text, line, begidx, endidx):
        s = line.split()
        if len(s) > 2:
            return []
        if (len(s) == 1 and line[-1] == " ") or (len(s) == 2 and line[-1] != " "):
            if len(s) > 1:
                return [i[len(s[1]) - len(text):] for i in glob.glob(s[1] + "*/") + glob.glob(s[1] + "*.stl")]
            else:
                return glob.glob("*/") + glob.glob("*.stl")

    def help_slice(self):
        self.log("Creates a gcode file from an stl model using the slicer (with tab-completion)")
        self.log("slice filename.stl - create gcode file")
        self.log("slice filename.stl view - create gcode file and view using skeiniso (if using skeinforge)")
        self.log("slice set - adjust slicer settings")

    #  --------------------------------------------------------------
    #  Print/upload handling
    #  --------------------------------------------------------------

    def do_upload(self, l):
        names = l.split()
        if len(names) == 2:
            filename = names[0]
            targetname = names[1]
        else:
            self.logError("Please enter target name in 8.3 format.")
            return
        if not self.p.online:
            self.logError("Not connected to printer.")
            return
        self._do_load(filename)
        self.log("Uploading as %s" % targetname)
        self.log("Uploading %s" % self.filename)
        self.p.send_now("M28 " + targetname)
        self.log("Press Ctrl-C to interrupt upload.")
        self.p.startprint(self.fgcode)
        try:
            sys.stdout.write("Progress: " + "00.0%")
            sys.stdout.flush()
            while self.p.printing:
                time.sleep(0.5)
                sys.stdout.write("\b\b\b\b\b%04.1f%%" % (100 * float(self.p.queueindex) / len(self.p.mainqueue),))
                sys.stdout.flush()
            self.p.send_now("M29 " + targetname)
            time.sleep(0.2)
            self.p.clear = True
            self._do_ls(False)
            self.log("\b\b\b\b\b100%.")
            self.log("Upload completed. %s should now be on the card." % targetname)
            return
        except (KeyboardInterrupt, Exception) as e:
            if isinstance(e, KeyboardInterrupt):
                self.logError("...interrupted!")
            else:
                self.logError("Something wrong happened while uploading:"
                              + "\n" + traceback.format_exc())
            self.p.pause()
            self.p.send_now("M29 " + targetname)
            time.sleep(0.2)
            self.p.cancelprint()
            self.logError("A partial file named %s may have been written to the sd card." % targetname)

    def complete_upload(self, text, line, begidx, endidx):
        s = line.split()
        if len(s) > 2:
            return []
        if (len(s) == 1 and line[-1] == " ") or (len(s) == 2 and line[-1] != " "):
            if len(s) > 1:
                return [i[len(s[1]) - len(text):] for i in glob.glob(s[1] + "*/") + glob.glob(s[1] + "*.g*")]
            else:
                return glob.glob("*/") + glob.glob("*.g*")

    def help_upload(self):
        self.log("Uploads a gcode file to the sd card")

    def help_print(self):
        if not self.fgcode:
            self.log("Send a loaded gcode file to the printer. Load a file with the load command first.")
        else:
            self.log("Send a loaded gcode file to the printer. You have %s loaded right now." % self.filename)

    def do_print(self, l):
        if not self.fgcode:
            self.logError("No file loaded. Please use load first.")
            return
        if not self.p.online:
            self.logError("Not connected to printer.")
            return
        self.log("Printing %s" % self.filename)
        self.log("You can monitor the print with the monitor command.")
        self.sdprinting = False
        self.p.startprint(self.fgcode)

    def do_pause(self, l):
        if self.sdprinting:
            self.p.send_now("M25")
        else:
            if not self.p.printing:
                self.logError("Not printing, cannot pause.")
                return
            self.p.pause()
        self.paused = True

    def help_pause(self):
        self.log("Pauses a running print")

    def pause(self, event = None):
        return self.do_pause(None)

    def do_resume(self, l):
        if not self.paused:
            self.logError("Not paused, unable to resume. Start a print first.")
            return
        self.paused = False
        if self.sdprinting:
            self.p.send_now("M24")
            return
        else:
            self.p.resume()

    def help_resume(self):
        self.log("Resumes a paused print.")

    def listfiles(self, line):
        if "Begin file list" in line:
            self.sdlisting = 1
        elif "End file list" in line:
            self.sdlisting = 0
            self.recvlisteners.remove(self.listfiles)
            if self.sdlisting_echo:
                self.log("Files on SD card:")
                self.log("\n".join(self.sdfiles))
        elif self.sdlisting:
            self.sdfiles.append(re.sub(" \d+$","",line.strip().lower()))

    def _do_ls(self, echo):
        # FIXME: this was 2, but I think it should rather be 0 as in do_upload
        self.sdlisting = 0
        self.sdlisting_echo = echo
        self.sdfiles = []
        self.recvlisteners.append(self.listfiles)
        self.p.send_now("M20")

    def do_ls(self, l):
        if not self.p.online:
            self.logError("Printer is not online. Please connect to it first.")
            return
        self._do_ls(True)

    def help_ls(self):
        self.log("Lists files on the SD card")

    def waitforsdresponse(self, l):
        if "file.open failed" in l:
            self.logError("Opening file failed.")
            self.recvlisteners.remove(self.waitforsdresponse)
            return
        if "File opened" in l:
            self.log(l)
        if "File selected" in l:
            self.log("Starting print")
            self.p.send_now("M24")
            self.sdprinting = True
            # self.recvlisteners.remove(self.waitforsdresponse)
            return
        if "Done printing file" in l:
            self.log(l)
            self.sdprinting = False
            self.recvlisteners.remove(self.waitforsdresponse)
            return
        if "SD printing byte" in l:
            # M27 handler
            try:
                resp = l.split()
                vals = resp[-1].split("/")
                self.percentdone = 100.0 * int(vals[0]) / int(vals[1])
            except:
                pass

    def do_reset(self, l):
        self.p.reset()

    def help_reset(self):
        self.log("Resets the printer.")

    def do_sdprint(self, l):
        if not self.p.online:
            self.log("Printer is not online. Please connect to it first.")
            return
        self._do_ls(False)
        while self.listfiles in self.recvlisteners:
            time.sleep(0.1)
        if l.lower() not in self.sdfiles:
            self.log("File is not present on card. Please upload it first.")
            return
        self.recvlisteners.append(self.waitforsdresponse)
        self.p.send_now("M23 " + l.lower())
        self.log("Printing file: %s from SD card." % l.lower())
        self.log("Requesting SD print...")
        time.sleep(1)

    def help_sdprint(self):
        self.log("Print a file from the SD card. Tab completes with available file names.")
        self.log("sdprint filename.g")

    def complete_sdprint(self, text, line, begidx, endidx):
        if not self.sdfiles and self.p.online:
            self._do_ls(False)
            while self.listfiles in self.recvlisteners:
                time.sleep(0.1)
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in self.sdfiles if i.startswith(text)]

    #  --------------------------------------------------------------
    #  Printcore callbacks
    #  --------------------------------------------------------------

    def startcb(self, resuming = False):
        self.starttime = time.time()
        if resuming:
            self.log("Print resumed at: %s" % format_time(self.starttime))
        else:
            self.log("Print started at: %s" % format_time(self.starttime))
            if not self.sdprinting:
                self.compute_eta = RemainingTimeEstimator(self.fgcode)
            else:
                self.compute_eta = None

            if self.settings.start_command:
                output = get_command_output(self.settings.start_command,
                                            {"$s": str(self.filename),
                                             "$t": format_time(time.time())})
                if output:
                    self.log("Start command output:")
                    self.log(output.rstrip())
        try:
            powerset_print_start(reason = "Preventing sleep during print")
        except:
            self.logError("Failed to set power settings:"
                          + "\n" + traceback.format_exc())

    def endcb(self):
        try:
            powerset_print_stop()
        except:
            self.logError("Failed to set power settings:"
                          + "\n" + traceback.format_exc())
        if self.p.queueindex == 0:
            print_duration = int(time.time() - self.starttime + self.extra_print_time)
            self.log("Print ended at: %(end_time)s and took %(duration)s" % {"end_time": format_time(time.time()),
                                                                                "duration": format_duration(print_duration)})

            # Update total filament length used
            if self.fgcode is not None:
                new_total = self.settings.total_filament_used + self.fgcode.filament_length
                self.set("total_filament_used", new_total)

            if not self.settings.final_command:
                return
            output = get_command_output(self.settings.final_command,
                                        {"$s": str(self.filename),
                                         "$t": format_duration(print_duration)})
            if output:
                self.log("Final command output:")
                self.log(output.rstrip())

    def recvcb_report(self, l):
        isreport = REPORT_NONE
        if "ok C:" in l or " Count " in l \
           or ("X:" in l and len(gcoder.m114_exp.findall(l)) == 6):
            self.posreport = l
            isreport = REPORT_POS
            if self.userm114 > 0:
                self.userm114 -= 1
                isreport |= REPORT_MANUAL
        return isreport

    def recvcb_actions(self, l):
        if l.startswith("!!"):
            self.do_pause(None)
            msg = l.split(" ", 1)
            if len(msg) > 1 and self.silent is False: self.logError(msg[1].ljust(15))
            sys.stdout.write(self.promptf())
            sys.stdout.flush()
            return True
        elif l.startswith("//"):
            command = l.split(" ", 1)
            if len(command) > 1:
                command = command[1]
                self.log("Received command %s" % command)
                command = command.split(":")
                if len(command) == 2 and command[0] == "action":
                    command = command[1]
                    if command == "pause":
                        self.do_pause(None)
                        sys.stdout.write(self.promptf())
                        sys.stdout.flush()
                        return True
                    elif command == "resume":
                        self.do_resume(None)
                        sys.stdout.write(self.promptf())
                        sys.stdout.flush()
                        return True
                    elif command == "disconnect":
                        self.do_disconnect(None)
                        sys.stdout.write(self.promptf())
                        sys.stdout.flush()
                        return True
        return False

    def recvcb(self, l):
        l = l.rstrip()
        for listener in self.recvlisteners:
            listener(l)
        if not self.recvcb_actions(l):
            report_type = self.recvcb_report(l)
            if not self.lineignorepattern.match(l) and l[:4] != "wait" and not self.sdlisting \
               and not self.monitoring and (report_type == REPORT_NONE or report_type & REPORT_MANUAL):
                if l[:5] == "echo:":
                    l = l[5:].lstrip()
                if self.silent is False: self.log("\r" + l.ljust(15))
                sys.stdout.write(self.promptf())
                sys.stdout.flush()

    def layer_change_cb(self, newlayer):
        layerz = self.fgcode.all_layers[newlayer].z
        if layerz is not None:
            self.curlayer = layerz
        if self.compute_eta:
            secondselapsed = int(time.time() - self.starttime + self.extra_print_time)
            self.compute_eta.update_layer(newlayer, secondselapsed)

    def get_eta(self):
        if self.sdprinting or self.uploading:
            if self.uploading:
                fractioncomplete = float(self.p.queueindex) / len(self.p.mainqueue)
            else:
                fractioncomplete = float(self.percentdone / 100.0)
            secondselapsed = int(time.time() - self.starttime + self.extra_print_time)
            # Prevent division by zero
            secondsestimate = secondselapsed / max(fractioncomplete, 0.000001)
            secondsremain = secondsestimate - secondselapsed
            progress = fractioncomplete
        elif self.compute_eta is not None:
            secondselapsed = int(time.time() - self.starttime + self.extra_print_time)
            secondsremain, secondsestimate = self.compute_eta(self.p.queueindex, secondselapsed)
            progress = self.p.queueindex
        else:
            secondsremain, secondsestimate, progress = 1, 1, 0
        return secondsremain, secondsestimate, progress

    def do_eta(self, l):
        if not self.p.printing:
            self.logError("Printer is not currently printing. No ETA available.")
        else:
            secondsremain, secondsestimate, progress = self.get_eta()
            eta = "Est: %s of %s remaining" % (format_duration(secondsremain),
                                                  format_duration(secondsestimate))
            self.log(eta.strip())

    def help_eta(self):
        self.log("Displays estimated remaining print time.")

    #  --------------------------------------------------------------
    #  Manual printer controls
    #  --------------------------------------------------------------

    def do_tool(self, l):
        tool = None
        try:
            tool = int(l.lower().strip())
        except:
            self.logError("You must specify the tool index as an integer.")
        if tool is not None and tool >= 0:
            if self.p.online:
                self.p.send_now("T%d" % tool)
                self.log("Using tool %d." % tool)
                self.current_tool = tool
            else:
                self.logError("Printer is not online.")
        else:
            self.logError("You cannot set negative tool numbers.")

    def help_tool(self):
        self.log("Switches to the specified tool (e.g. doing tool 1 will emit a T1 G-Code).")

    def do_move(self, l):
        if len(l.split()) < 2:
            self.logError("No move specified.")
            return
        if self.p.printing:
            self.logError("Printer is currently printing. Please pause the print before you issue manual commands.")
            return
        if not self.p.online:
            self.logError("Printer is not online. Unable to move.")
            return
        l = l.split()
        if l[0].lower() == "x":
            feed = self.settings.xy_feedrate
            axis = "X"
        elif l[0].lower() == "y":
            feed = self.settings.xy_feedrate
            axis = "Y"
        elif l[0].lower() == "z":
            feed = self.settings.z_feedrate
            axis = "Z"
        elif l[0].lower() == "e":
            feed = self.settings.e_feedrate
            axis = "E"
        else:
            self.logError("Unknown axis.")
            return
        try:
            float(l[1])  # check if distance can be a float
        except:
            self.logError("Invalid distance")
            return
        try:
            feed = int(l[2])
        except:
            pass
        self.p.send_now("G91")
        self.p.send_now("G0 " + axis + str(l[1]) + " F" + str(feed))
        self.p.send_now("G90")

    def help_move(self):
        self.log("Move an axis. Specify the name of the axis and the amount. ")
        self.log("move X 10 will move the X axis forward by 10mm at %s mm/min (default XY speed)" % self.settings.xy_feedrate)
        self.log("move Y 10 5000 will move the Y axis forward by 10mm at 5000mm/min")
        self.log("move Z -1 will move the Z axis down by 1mm at %s mm/min (default Z speed)" % self.settings.z_feedrate)
        self.log("Common amounts are in the tabcomplete list.")

    def complete_move(self, text, line, begidx, endidx):
        if (len(line.split()) == 2 and line[-1] != " ") or (len(line.split()) == 1 and line[-1] == " "):
            return [i for i in ["X ", "Y ", "Z ", "E "] if i.lower().startswith(text)]
        elif len(line.split()) == 3 or (len(line.split()) == 2 and line[-1] == " "):
            base = line.split()[-1]
            rlen = 0
            if base.startswith("-"):
                rlen = 1
            if line[-1] == " ":
                base = ""
            return [i[rlen:] for i in ["-100", "-10", "-1", "-0.1", "100", "10", "1", "0.1", "-50", "-5", "-0.5", "50", "5", "0.5", "-200", "-20", "-2", "-0.2", "200", "20", "2", "0.2"] if i.startswith(base)]
        else:
            return []

    def do_extrude(self, l, override = None, overridefeed = 300):
        length = self.settings.default_extrusion  # default extrusion length
        feed = self.settings.e_feedrate  # default speed
        if not self.p.online:
            self.logError("Printer is not online. Unable to extrude.")
            return
        if self.p.printing:
            self.logError("Printer is currently printing. Please pause the print before you issue manual commands.")
            return
        ls = l.split()
        if len(ls):
            try:
                length = float(ls[0])
            except:
                self.logError("Invalid length given.")
        if len(ls) > 1:
            try:
                feed = int(ls[1])
            except:
                self.logError("Invalid speed given.")
        if override is not None:
            length = override
            feed = overridefeed
        self.do_extrude_final(length, feed)

    def do_extrude_final(self, length, feed):
        if length > 0:
            self.log("Extruding %fmm of filament." % (length,))
        elif length < 0:
            self.log("Reversing %fmm of filament." % (-length,))
        else:
            self.log("Length is 0, not doing anything.")
        self.p.send_now("G91")
        self.p.send_now("G1 E" + str(length) + " F" + str(feed))
        self.p.send_now("G90")

    def do_retract(self):
        self.p.send_now("G10")

    def do_recover(self):
        self.p.send_now("G11")

    def do_dwell_ms(self, time):
        self.p.send_now("G4 P" + str(int(time))) # ms

    def help_extrude(self):
        self.log("Extrudes a length of filament, 5mm by default, or the number of mm given as a parameter")
        self.log("extrude - extrudes 5mm of filament at 300mm/min (5mm/s)")
        self.log("extrude 20 - extrudes 20mm of filament at 300mm/min (5mm/s)")
        self.log("extrude -5 - REVERSES 5mm of filament at 300mm/min (5mm/s)")
        self.log("extrude 10 210 - extrudes 10mm of filament at 210mm/min (3.5mm/s)")

    def do_reverse(self, l):
        length = self.settings.default_extrusion  # default extrusion length
        feed = self.settings.e_feedrate  # default speed
        if not self.p.online:
            self.logError("Printer is not online. Unable to reverse.")
            return
        if self.p.printing:
            self.logError("Printer is currently printing. Please pause the print before you issue manual commands.")
            return
        ls = l.split()
        if len(ls):
            try:
                length = float(ls[0])
            except:
                self.logError("Invalid length given.")
        if len(ls) > 1:
            try:
                feed = int(ls[1])
            except:
                self.logError("Invalid speed given.")
        self.do_extrude("", -length, feed)

    def help_reverse(self):
        self.log("Reverses the extruder, 5mm by default, or the number of mm given as a parameter")
        self.log("reverse - reverses 5mm of filament at 300mm/min (5mm/s)")
        self.log("reverse 20 - reverses 20mm of filament at 300mm/min (5mm/s)")
        self.log("reverse 10 210 - extrudes 10mm of filament at 210mm/min (3.5mm/s)")
        self.log("reverse -5 - EXTRUDES 5mm of filament at 300mm/min (5mm/s)")

    def do_home(self, l):
        if not self.p.online:
            self.logError("Printer is not online. Unable to move.")
            return
        if self.p.printing:
            self.logError("Printer is currently printing. Please pause the print before you issue manual commands.")
            return
        if "x" in l.lower():
            self.p.send_now("G28 X0")
        if "y" in l.lower():
            self.p.send_now("G28 Y0")
        if "z" in l.lower():
            self.p.send_now("G28 Z0")
        if "e" in l.lower():
            self.p.send_now("G92 E0")
        if not len(l):
            self.p.send_now("G28")
            self.p.send_now("G92 E0")

    def help_home(self):
        self.log("Homes the printer")
        self.log("home - homes all axes and zeroes the extruder(Using G28 and G92)")
        self.log("home xy - homes x and y axes (Using G28)")
        self.log("home z - homes z axis only (Using G28)")
        self.log("home e - set extruder position to zero (Using G92)")
        self.log("home xyze - homes all axes and zeroes the extruder (Using G28 and G92)")

    def do_off(self, l):
        self.off()

    def off(self, ignore = None):
        if self.p.online:
            if self.p.printing: self.pause(None)
            self.log("; Motors off")
            self.onecmd("M84")
            self.log("; Extruder off")
            self.onecmd("M104 S0")
            self.log("; Heatbed off")
            self.onecmd("M140 S0")
            self.log("; Fan off")
            self.onecmd("M107")
            self.log("; Power supply off")
            self.onecmd("M81")
        else:
            self.logError("Printer is not online. Unable to turn it off.")

    def help_off(self):
        self.log("Turns off everything on the printer")

    #  --------------------------------------------------------------
    #  Host commands handling
    #  --------------------------------------------------------------

    def process_host_command(self, command):
        """Override host command handling"""
        command = command.lstrip()
        if command.startswith(";@"):
            command = command[2:]
            self.log("G-Code calling host command \"%s\"" % command)
            self.onecmd(command)

    def do_run_script(self, l):
        p = run_command(l, {"$s": str(self.filename)}, stdout = subprocess.PIPE, universal_newlines = True)
        for line in p.stdout.readlines():
            self.log("<< " + line.strip())

    def help_run_script(self):
        self.log("Runs a custom script. Current gcode filename can be given using $s token.")

    def do_run_gcode_script(self, l):
        try:
            self.fgcode = RGSGCoder(l)
            self.do_print(None)
        except BaseException as e:
            self.logError(traceback.format_exc())

    def help_run_gcode_script(self):
        self.log("Runs a custom script which output gcode which will in turn be executed. Current gcode filename can be given using $s token.")

    def complete_run_gcode_script(self, text, line, begidx, endidx):
        words = line.split()
        sep = os.path.sep
        if len(words) < 2:
            return ['.' + sep , sep]
        corrected_text = words[-1] # text arg skips leading '/', include it
        if corrected_text == '.':
            return ['./'] # guide user that in linux, PATH does not include . and relative executed scripts must start with ./
        prefix_len = len(corrected_text) - len(text)
        res = [((f + sep) if os.path.isdir(f) else f)[prefix_len:] #skip unskipped prefix_len
                for f in glob.glob(corrected_text + '*')]
        return res
