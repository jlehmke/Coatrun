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

import traceback
import logging

import wx

class BaseViz:
    def clear(self, *a):
        pass

    def addfile_perlayer(self, gcode, showall = False):
        layer_idx = 0
        while layer_idx < len(gcode.all_layers):
            yield layer_idx
            layer_idx += 1
        yield None

    def addfile(self, *a, **kw):
        pass

    def addgcodehighlight(self, *a, **kw):
        pass

    def setlayer(self, *a):
        pass

    def on_settings_change(self, changed_settings):
        pass

class NoViz(BaseViz):
    showall = False
    def Refresh(self, *a):
        pass

class NoVizWindow:

    def __init__(self):
        self.p = NoViz()

    def Destroy(self):
        pass

class VizPane(wx.BoxSizer):

    def __init__(self, root, parentpanel = None):
        super(VizPane, self).__init__(wx.VERTICAL)
        if not parentpanel: parentpanel = root.panel
        
        from printrun import gviz
        root.gviz = gviz.Gviz(parentpanel, (300, 300),
                                build_dimensions = root.build_dimensions_list,
                                grid = (root.settings.preview_grid_step1, root.settings.preview_grid_step2),
                                extrusion_width = root.settings.preview_extrusion_width,
                                bgcolor = root.bgcolor)
        #root.gviz.SetToolTip(wx.ToolTip("Click to examine / edit\n  layers of loaded file"))
        root.gviz.showall = 1

        if not isinstance(root.gviz, NoViz):
            self.Add(root.gviz.widget, 1, flag = wx.EXPAND)
