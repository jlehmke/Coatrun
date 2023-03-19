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

import wx

from .xybuttons import XYButtons
from .zbuttons import ZButtons
from wx.lib.agw.floatspin import FloatSpin

from .utils import make_button, make_custom_button

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
        "ebuttons": (1 + 2 + 0, 0),
        "esettings": (1 + 2 + 1, 0),
        "speedcontrol": (1 + 2 + 2, 0),
        "extrude": (3, 0),
        "reverse": (3, 2),
    }

    span_mapping = {
        "ebuttons": (1, 6),
        "esettings": (1, 6),
        "speedcontrol": (1, 6),
        "extrude": (1, 2),
        "reverse": (1, 3),
    }

    if mini_mode:
        pos_mapping["etool_label"] = (0, 0)
        pos_mapping["etool_val"] = (0, 1)
        pos_mapping["edist_label"] = (0, 2)
        pos_mapping["edist_val"] = (0, 3)
        pos_mapping["edist_unit"] = (0, 4)
    else:
        pos_mapping["edist_label"] = (0, 0)
        pos_mapping["edist_val"] = (1, 0)
        pos_mapping["edist_unit"] = (1, 1)
        pos_mapping["efeed_label"] = (0, 2)
        pos_mapping["efeed_val"] = (1, 2)
        pos_mapping["efeed_unit"] = (1, 3)

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
    root.speed_setbtn = make_button(speedpanel, "Set", speedslider_set, "Set print speed factor", size = (38, -1), style = wx.BU_EXACTFIT)
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

    # Extrusion settings
    esettingspanel = root.newPanel(parentpanel)
    esettingssizer = wx.GridBagSizer()
    esettingssizer.SetEmptyCellSize((0, 0))
    root.edist = wx.SpinCtrlDouble(esettingspanel, -1, initial = root.settings.last_extrusion, min = 0, max = 1000, size = (135, -1))
    root.edist.SetDigits(1)
    root.edist.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
    root.edist.SetBackgroundColour((225, 200, 200))
    root.edist.SetForegroundColour("black")
    root.edist.Bind(wx.EVT_TEXT, root.setfeeds)
    add("edist_label", wx.StaticText(esettingspanel, -1, "Length:"), container = esettingssizer, flag = wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, border = 5)
    add("edist_val", root.edist, container = esettingssizer, flag = wx.ALIGN_CENTER | wx.RIGHT, border = 5)
    unit_label = "mm" if mini_mode else "mm @"
    add("edist_unit", wx.StaticText(esettingspanel, -1, unit_label), container = esettingssizer, flag = wx.ALIGN_CENTER | wx.RIGHT, border = 5)
    root.edist.SetToolTip(wx.ToolTip("Amount to Extrude or Retract (mm)"))
    if not mini_mode:
        root.efeedc = wx.SpinCtrlDouble(esettingspanel, -1, initial = root.settings.e_feedrate, min = 0, max = 50000, size = (145, -1))
        root.efeedc.SetDigits(1)
        root.efeedc.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
        root.efeedc.SetToolTip(wx.ToolTip("Extrude / Retract speed (mm/min)"))
        root.efeedc.SetBackgroundColour((225, 200, 200))
        root.efeedc.SetForegroundColour("black")
        root.efeedc.Bind(wx.EVT_TEXT, root.setfeeds)
        add("efeed_val", root.efeedc, container = esettingssizer, flag = wx.ALIGN_CENTER | wx.RIGHT, border = 5)
        add("efeed_label", wx.StaticText(esettingspanel, -1, "Speed:"), container = esettingssizer, flag = wx.ALIGN_LEFT)
        add("efeed_unit", wx.StaticText(esettingspanel, -1, "mm/\nmin"), container = esettingssizer, flag = wx.ALIGN_CENTER)
    else:
        root.efeedc = None
    esettingspanel.SetSizer(esettingssizer)
    add("esettings", esettingspanel, flag = wx.ALIGN_LEFT)

    if not standalone_mode:
        ebuttonspanel = root.newPanel(parentpanel)
        ebuttonssizer = wx.BoxSizer(wx.HORIZONTAL)
        if root.settings.extruders > 1:
            etool_sel_panel = esettingspanel if mini_mode else ebuttonspanel
            etool_label = wx.StaticText(etool_sel_panel, -1, "Tool:")
            if root.settings.extruders == 2:
                root.extrudersel = wx.Button(etool_sel_panel, -1, "0", style = wx.BU_EXACTFIT)
                root.extrudersel.SetToolTip(wx.ToolTip("Click to switch current extruder"))

                def extrudersel_cb(event):
                    if root.extrudersel.GetLabel() == "1":
                        new = "0"
                    else:
                        new = "1"
                    root.extrudersel.SetLabel(new)
                    root.tool_change(event)
                root.extrudersel.Bind(wx.EVT_BUTTON, extrudersel_cb)
                root.extrudersel.GetValue = root.extrudersel.GetLabel
                root.extrudersel.SetValue = root.extrudersel.SetLabel
            else:
                choices = [str(i) for i in range(0, root.settings.extruders)]
                root.extrudersel = wx.ComboBox(etool_sel_panel, -1, choices = choices,
                                               style = wx.CB_DROPDOWN | wx.CB_READONLY,
                                               size = (50, -1))
                root.extrudersel.SetToolTip(wx.ToolTip("Select current extruder"))
                root.extrudersel.SetValue(choices[0])
                root.extrudersel.Bind(wx.EVT_COMBOBOX, root.tool_change)
            root.printerControls.append(root.extrudersel)
            if mini_mode:
                add("etool_label", etool_label, container = esettingssizer, flag = wx.ALIGN_CENTER)
                add("etool_val", root.extrudersel, container = esettingssizer)
            else:
                ebuttonssizer.Add(etool_label, flag = wx.ALIGN_CENTER)
                ebuttonssizer.Add(root.extrudersel)

        for key in ["extrude", "reverse"]:
            desc = root.cpbuttons[key]
            btn = make_custom_button(root, ebuttonspanel, desc,
                                     style = wx.BU_EXACTFIT)
            ebuttonssizer.Add(btn, 1, flag = wx.EXPAND)

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
            btn = make_custom_button(root, panel, desc)
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
