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

class LogPane(wx.BoxSizer):

    def __init__(self, root, parentpanel = None):
        super(LogPane, self).__init__(wx.VERTICAL)
        if not parentpanel: parentpanel = root.panel
        root.logbox = wx.TextCtrl(parentpanel, style = wx.TE_MULTILINE, size = (350, -1))
        root.logbox.SetMinSize((100, -1))
        root.logbox.SetEditable(0)
        self.Add(root.logbox, 1, wx.EXPAND)
        bottom_panel = root.newPanel(parentpanel)
        lbrs = wx.BoxSizer(wx.HORIZONTAL)
        root.commandbox = wx.TextCtrl(bottom_panel, style = wx.TE_PROCESS_ENTER)
        root.commandbox.SetToolTip(wx.ToolTip("Send commands to printer\n(Type 'help' for simple\nhelp function)"))
        root.commandbox.Hint = 'Command to [S]end'
        root.commandbox.Bind(wx.EVT_TEXT_ENTER, root.sendline)
        root.commandbox.Bind(wx.EVT_CHAR, root.cbkey)
        def deselect(ev):
            # In Ubuntu 19.10, when focused, all text is selected
            lp = root.commandbox.LastPosition
            # print(f"SetSelection({lp}, {lp})")
            wx.CallAfter(root.commandbox.SetSelection, lp, lp)
            ev.Skip()
        root.commandbox.Bind(wx.EVT_SET_FOCUS, deselect)
        root.commandbox.history = [""]
        root.commandbox.histindex = 1
        lbrs.Add(root.commandbox, 1)
        
        root.sendbtn = wx.Button(bottom_panel, -1, "Send")
        root.sendbtn.Bind(wx.EVT_BUTTON, root.sendline)
        root.sendbtn.SetToolTip(wx.ToolTip("Send Command to Printer"))
        lbrs.Add(root.sendbtn)

        bottom_panel.SetSizer(lbrs)
        self.Add(bottom_panel, 0, wx.EXPAND)
