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

def MainToolbar(root, parentpanel = None, use_wrapsizer = False):
    if not parentpanel: parentpanel = root.panel
    if root.settings.lockbox:
        root.locker = wx.CheckBox(parentpanel, label = "Lock" + "  ")
        root.locker.Bind(wx.EVT_CHECKBOX, root.lock)
        root.locker.SetToolTip(wx.ToolTip("Lock graphical interface"))
        glob = wx.BoxSizer(wx.HORIZONTAL)
        parentpanel = root.newPanel(parentpanel)
        glob.Add(parentpanel, 1, flag = wx.EXPAND)
        glob.Add(root.locker, 0, flag = wx.ALIGN_CENTER)
    ToolbarSizer = wx.WrapSizer if use_wrapsizer else wx.BoxSizer
    self = ToolbarSizer(wx.HORIZONTAL)
    root.rescanbtn = wx.Button(parentpanel, -1, "Port", size = (-1, -1), style = wx.BU_EXACTFIT)
    root.rescanbtn.Bind(wx.EVT_BUTTON, root.rescanports)
    root.rescanbtn.SetToolTip(wx.ToolTip("Communication Settings\nClick to rescan ports"))

    self.Add(root.rescanbtn, 0, wx.ALIGN_CENTER | wx.LEFT, 0)

    root.serialport = wx.ComboBox(parentpanel, -1, choices = root.scanserial(),
                                  style = wx.CB_DROPDOWN)
    root.serialport.SetToolTip(wx.ToolTip("Select Port Printer is connected to"))
    root.rescanports()
    self.Add(root.serialport, 0, wx.ALIGN_CENTER, 0)

    self.Add(wx.StaticText(parentpanel, -1, "@"), 0, wx.RIGHT | wx.ALIGN_CENTER, 0)
    root.baud = wx.ComboBox(parentpanel, -1,
                            choices = ["2400", "9600", "19200", "38400",
                                       "57600", "115200", "250000"],
                            style = wx.CB_DROPDOWN, size = (110, -1))
    root.baud.SetToolTip(wx.ToolTip("Select Baud rate for printer communication"))
    try:
        root.baud.SetValue("115200")
        root.baud.SetValue(str(root.settings.baudrate))
    except:
        pass
    self.Add(root.baud, 0, wx.ALIGN_CENTER, 0)

    if not hasattr(root, "connectbtn"):
        root.connectbtn_cb_var = root.connect
        root.connectbtn = wx.Button(parentpanel, -1, "&Connect", size = (-1, -1))
        root.connectbtn.Bind(wx.EVT_BUTTON, root.connectbtn_cb)
        root.connectbtn.SetToolTip(wx.ToolTip("Connect to the printer"))
        root.statefulControls.append(root.connectbtn)
    else:
        root.connectbtn.Reparent(parentpanel)
    self.Add(root.connectbtn, 0, wx.ALIGN_CENTER, 0)
    if not hasattr(root, "resetbtn"):
        root.resetbtn = wx.Button(parentpanel, -1, "Reset", size = (-1, -1))
        root.resetbtn.Bind(wx.EVT_BUTTON, root.reset)
        root.resetbtn.SetToolTip(wx.ToolTip("Reset the printer"))
        root.statefulControls.append(root.resetbtn)
    else:
        root.resetbtn.Reparent(parentpanel)
    self.Add(root.resetbtn, 0, wx.ALIGN_CENTER, 0)

    self.AddStretchSpacer(prop = 1)

    self.toolbar = wx.ToolBar(parentpanel, -1, style = wx.TB_HORIZONTAL | wx.BORDER_SIMPLE | wx.TB_HORZ_TEXT)

    root.loadbtn = self.toolbar.AddTool(1, 'Load file', wx.Image('images/import.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), "Load a mask file",)
    self.toolbar.Bind(wx.EVT_TOOL, root.loadfile, id=1)

    root.printbtn = self.toolbar.AddTool(2, 'Print', wx.Image('images/control-start.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), "Start job",)
    self.toolbar.Bind(wx.EVT_TOOL, root.printfile, id=2)

    root.pausebtn = self.toolbar.AddTool(3, 'Pause', wx.Image('images/control-pause.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), "Pause job",)
    self.toolbar.Bind(wx.EVT_TOOL, root.pause, id=3)

    root.offbtn = self.toolbar.AddTool(4, 'Off', wx.Image('images/power_button_off.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), "Turn printer off",)
    self.toolbar.Bind(wx.EVT_TOOL, root.off, id=4)

    root.offbtn = self.toolbar.AddTool(5, 'Edit', wx.Image('images/edit.png', wx.BITMAP_TYPE_PNG).ConvertToBitmap(), "Edit G-Code",)
    self.toolbar.Bind(wx.EVT_TOOL, root.show_edit_layer, id=5)

    self.Add(self.toolbar, 0, border = 5)
    
    self.AddStretchSpacer(prop = 4)

    if root.settings.lockbox:
        parentpanel.SetSizer(self)
        return glob
    else:
        return self
