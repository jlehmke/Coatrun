# This file is part of the Coatrun suite.
#
# Coatrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Coatrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Coatrun.  If not, see <http://www.gnu.org/licenses/>.

import wx

from .xybuttons import XYButtons
from .zbuttons import ZButtons
from wx.lib.agw.floatspin import FloatSpin

class XYZControlsSizer(wx.GridBagSizer):

    def __init__(self, root, parentpanel = None):
        super(XYZControlsSizer, self).__init__()
        if not parentpanel: parentpanel = root.panel
        root.xyb = XYButtons(parentpanel, root.moveXY, root.homeButtonClicked, root.spacebarAction, root.bgcolor, zcallback=root.moveZ)
        root.xyb.SetToolTip('[J]og controls. (Shift)+TAB ESC Shift/Ctrl+(arrows PgUp/PgDn)')
        self.Add(root.xyb, pos = (0, 1), flag = wx.ALIGN_CENTER)
        root.zb = ZButtons(parentpanel, root.moveZ, root.bgcolor)
        self.Add(root.zb, pos = (0, 2), flag = wx.ALIGN_CENTER)

def add_extra_controls(self, root, parentpanel, extra_buttons = None, mini_mode = False):
    standalone_mode = extra_buttons is not None

    pos_mapping = {
        "ebuttons": (3, 0),
        "speedcontrol": (5, 0),
        "extrude": (3, 0),
        "reverse": (3, 2),
    }

    span_mapping = {
        "ebuttons": (1, 6),
        "speedcontrol": (1, 6),
        "extrude": (1, 2),
        "reverse": (1, 3),
    }

    def add(name, widget, *args, **kwargs):
        kwargs["pos"] = pos_mapping[name]
        if name in span_mapping:
            kwargs["span"] = span_mapping[name]
        if "container" in kwargs:
            container = kwargs["container"]
            del kwargs["container"]
        else:
            container = self
        container.Add(widget, *args, **kwargs)

    # Speed control #
    speedpanel = root.newPanel(parentpanel)
    speedsizer = wx.BoxSizer(wx.HORIZONTAL)
    speedsizer.Add(wx.StaticText(speedpanel, -1, "Print speed:"), flag = wx.ALIGN_CENTER_VERTICAL)

    root.speed_slider = wx.Slider(speedpanel, -1, 100, 1, 300)
    speedsizer.Add(root.speed_slider, 1, flag = wx.EXPAND)

    root.speed_spin = wx.SpinCtrlDouble(speedpanel, -1, initial = 100, min = 1, max = 300, style = wx.ALIGN_LEFT, size = (115, -1))
    root.speed_spin.SetDigits(0)
    speedsizer.Add(root.speed_spin, 0, flag = wx.ALIGN_CENTER_VERTICAL)
    root.speed_label = wx.StaticText(speedpanel, -1, "%")
    speedsizer.Add(root.speed_label, flag = wx.ALIGN_CENTER_VERTICAL)

    def speedslider_set(event):
        root.do_setspeed()
        root.speed_setbtn.SetBackgroundColour(wx.NullColour)
    root.speed_setbtn = wx.Button(speedpanel, -1, "Set", style = wx.BU_EXACTFIT, size = (38, -1))
    root.speed_setbtn.Bind(wx.EVT_BUTTON, speedslider_set)
    root.speed_setbtn.SetToolTip(wx.ToolTip("Set print speed factor"))
    root.printerControls.append(root.speed_setbtn)
    speedsizer.Add(root.speed_setbtn, flag = wx.ALIGN_CENTER)
    speedpanel.SetSizer(speedsizer)
    add("speedcontrol", speedpanel, flag = wx.EXPAND)

    def speedslider_spin(event):
        value = root.speed_spin.GetValue()
        root.speed_setbtn.SetBackgroundColour("red")
        root.speed_slider.SetValue(int(value))
    root.speed_spin.Bind(wx.EVT_SPINCTRLDOUBLE, speedslider_spin)

    def speedslider_scroll(event):
        value = root.speed_slider.GetValue()
        root.speed_setbtn.SetBackgroundColour("red")
        root.speed_spin.SetValue(value)
    root.speed_slider.Bind(wx.EVT_SCROLL, speedslider_scroll)

    # Extrusion controls #

    if not standalone_mode:
        ebuttonspanel = root.newPanel(parentpanel)
        ebuttonssizer = wx.BoxSizer(wx.HORIZONTAL)
        for key in ["extrude", "reverse"]:
            desc = root.cpbuttons[key]
            btn = wx.Button(ebuttonspanel, -1, desc.label, style = wx.BU_EXACTFIT)
            btn.Bind(wx.EVT_BUTTON, root.process_button,)
            btn.SetToolTip(wx.ToolTip(desc.tooltip))

            btn.SetBackgroundColour(desc.background)
            btn.SetForegroundColour("black")
            btn.properties = desc
            root.btndict[desc.command] = btn
            root.printerControls.append(btn)

            ebuttonssizer.Add(btn, 1, flag = wx.EXPAND)

        ebuttonssizer.AddSpacer(10)
        label = wx.StaticText(ebuttonspanel, -1, "Time:")
        ebuttonssizer.Add(label, flag = wx.ALIGN_CENTER)
        ebuttonssizer.AddSpacer(2)

        root.etime = wx.SpinCtrlDouble(ebuttonspanel, -1, initial = 1000, min = 0, max = 10000)
        root.etime.SetDigits(0)
        root.etime.SetIncrement(100)
        root.etime.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
        root.etime.SetToolTip(wx.ToolTip("Extrude time (s)"))
        #root.etime.SetBackgroundColour((225, 200, 200))
        root.etime.SetForegroundColour("black")
        root.etime.Bind(wx.EVT_TEXT, root.setfeeds)
        ebuttonssizer.Add(root.etime, flag = wx.ALIGN_CENTER | wx.RIGHT, border = 5)
      
        label = wx.StaticText(ebuttonspanel, -1, "ms")
        ebuttonssizer.Add(label, flag = wx.ALIGN_CENTER)


        ebuttonspanel.SetSizer(ebuttonssizer)
        add("ebuttons", ebuttonspanel, flag = wx.EXPAND)
    else:
        for key, btn in extra_buttons.items():
            add(key, btn, flag = wx.EXPAND)

class ControlsSizer(wx.GridBagSizer):

    def __init__(self, root, parentpanel = None, standalone_mode = False, mini_mode = False):
        super(ControlsSizer, self).__init__()
        if not parentpanel: parentpanel = root.panel
        else: self.make_standard(root, parentpanel, standalone_mode)

    def make_standard(self, root, parentpanel, standalone_mode):
        lltspanel = root.newPanel(parentpanel)
        llts = wx.BoxSizer(wx.HORIZONTAL)
        lltspanel.SetSizer(llts)
        self.Add(lltspanel, pos = (0, 0), span = (1, 6))
        xyzpanel = root.newPanel(parentpanel)
        self.xyzsizer = XYZControlsSizer(root, xyzpanel)
        xyzpanel.SetSizer(self.xyzsizer)
        self.Add(xyzpanel, pos = (1, 0), span = (1, 6), flag = wx.ALIGN_CENTER)

        self.extra_buttons = {}
        pos_mapping = {"extrude": (4, 0),
                       "reverse": (4, 2),
                       }
        span_mapping = {"extrude": (1, 2),
                        "reverse": (1, 3),
                        }
        for key, desc in root.cpbuttons.items():
            if not standalone_mode and key in ["extrude", "reverse"]:
                continue
            panel = lltspanel if key == "motorsoff" else parentpanel
            btn = wx.Button(panel, -1, desc.label)
            btn.Bind(wx.EVT_BUTTON, root.process_button,)
            btn.SetToolTip(wx.ToolTip(desc.tooltip))
            btn.SetBackgroundColour(desc.background)
            btn.SetForegroundColour("black")
            btn.properties = desc
            root.btndict[desc.command] = btn
            root.printerControls.append(btn)

            if key == "motorsoff":
                llts.Add(btn)
            elif not standalone_mode:
                self.Add(btn, pos = pos_mapping[key], span = span_mapping[key], flag = wx.EXPAND)
            else:
                self.extra_buttons[key] = btn

        root.xyfeedc = wx.SpinCtrl(lltspanel, -1, str(root.settings.xy_feedrate), min = 0, max = 50000, size = (130, -1))
        root.xyfeedc.SetToolTip(wx.ToolTip("Set Maximum Speed for X & Y axes (mm/min)"))
        llts.Add(wx.StaticText(lltspanel, -1, "XY:"), flag = wx.ALIGN_CENTER_VERTICAL)
        llts.Add(root.xyfeedc)
        llts.Add(wx.StaticText(lltspanel, -1, "mm/min Z:"), flag = wx.ALIGN_CENTER_VERTICAL)
        root.zfeedc = wx.SpinCtrl(lltspanel, -1, str(root.settings.z_feedrate), min = 0, max = 50000, size = (130, -1))
        root.zfeedc.SetToolTip(wx.ToolTip("Set Maximum Speed for Z axis (mm/min)"))
        llts.Add(root.zfeedc,)

        root.xyfeedc.Bind(wx.EVT_SPINCTRL, root.setfeeds)
        root.zfeedc.Bind(wx.EVT_SPINCTRL, root.setfeeds)
        root.xyfeedc.Bind(wx.EVT_TEXT, root.setfeeds)
        root.zfeedc.Bind(wx.EVT_TEXT, root.setfeeds)
        root.zfeedc.SetBackgroundColour((180, 255, 180))
        root.zfeedc.SetForegroundColour("black")

        if not standalone_mode:
            add_extra_controls(self, root, parentpanel, None)
