
import wx

class PcbPane(wx.GridBagSizer):

    def __init__(self, root, parentpanel = None):
        super(PcbPane, self).__init__(wx.VERTICAL)
        if not parentpanel: parentpanel = root.panel
        
        boldfont = wx.Font(wx.DEFAULT, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        
        row = 0
        p0 = root.newPanel(parentpanel)
        s0 = wx.BoxSizer(wx.HORIZONTAL)
        p0.SetSizer(s0)
        self.Add(p0, pos = (row, 0), span = (1, -1))
        text = wx.StaticText(p0, -1, "Position")
        s0.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        text.SetFont(boldfont)

        row += 1
        p1 = root.newPanel(parentpanel)
        s1 = wx.BoxSizer(wx.HORIZONTAL)
        p1.SetSizer(s1)
        self.Add(p1, pos = (row, 0), span = (1, -1))
        text = wx.StaticText(p1, -1, "Origin:")
        s1.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        s1.AddSpacer(10)

        text = wx.StaticText(p1, -1, "X:")
        s1.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        root.pcbx = wx.SpinCtrlDouble(p1, -1, str(100), min = -1000, max = 1000)
        root.pcbx.SetDigits(2)
        root.pcbx.SetIncrement(10)
        #root.pcbx.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
        root.pcbx.SetToolTip(wx.ToolTip("PCB origin in x-axis"))
        s1.Add(root.pcbx, 0, wx.ALIGN_CENTER | wx.LEFT, 0)
        s1.Add(wx.StaticText(p1, -1, "mm"), flag = wx.ALIGN_CENTER_VERTICAL)
        s1.AddSpacer(20)

        text = wx.StaticText(p1, -1, "Y:")
        s1.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        root.pcby = wx.SpinCtrlDouble(p1, -1, str(100), min = -1000, max = 1000)
        root.pcby.SetDigits(2)
        root.pcby.SetIncrement(10)
        #root.pcby.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
        root.pcby.SetToolTip(wx.ToolTip("PCB origin in y-axis"))
        s1.Add(root.pcby, 0, wx.ALIGN_CENTER | wx.LEFT, 0)
        s1.Add(wx.StaticText(p1, -1, "mm"), flag = wx.ALIGN_CENTER_VERTICAL)
        s1.AddSpacer(20)

        text = wx.StaticText(p1, -1, "Rot.:")
        s1.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        root.pcba = wx.SpinCtrlDouble(p1, -1, str(0), min = 0, max = 360)
        root.pcba.SetDigits(2)
        root.pcba.SetIncrement(10)
        #root.pcba.Bind(wx.EVT_SPINCTRLDOUBLE, root.setfeeds)
        root.pcba.SetToolTip(wx.ToolTip("PCB rotation angle"))
        s1.Add(root.pcba, 0, wx.ALIGN_CENTER | wx.LEFT, 0)
        s1.Add(wx.StaticText(p1, -1, "deg"), flag = wx.ALIGN_CENTER_VERTICAL)
        s1.AddSpacer(20)

        row += 1
        p2 = root.newPanel(parentpanel)
        s2 = wx.BoxSizer(wx.HORIZONTAL)
        p2.SetSizer(s2)
        self.Add(p2, pos = (row, 0), span = (1, -1))
        text = wx.StaticText(p2, -1, "Fiducials")
        s2.Add(text, flag = wx.ALIGN_CENTER_VERTICAL)
        text.SetFont(boldfont)

        row += 1
        p3 = root.newPanel(parentpanel)
        s3 = wx.BoxSizer(wx.HORIZONTAL)
        p3.SetSizer(s3)
        self.Add(p3, pos = (row, 0), span = (1, -1))
        fiducials = wx.ListCtrl(p3, style=wx.LC_REPORT, size=(-1,100))
        fiducials.InsertColumn(0, 'Use')
        fiducials.InsertColumn(1, 'Reference')
        fiducials.InsertColumn(2, 'X')
        fiducials.InsertColumn(3, 'Y')
        fiducials.EnableCheckBoxes(True)
        fiducials.Append(("","FID1", "12.250","42.500"))
        fiducials.Append(("","FID2", "52.250","62.500"))
        fiducials.Append(("","FID3", "52.250","92.500"))
        s3.Add(fiducials)

        row += 1
        p4 = root.newPanel(parentpanel)
        s4 = wx.BoxSizer(wx.HORIZONTAL)
        p4.SetSizer(s4)
        self.Add(p4, pos = (row, 0), span = (1, -1))
        root.applybtn = wx.Button(p4, -1, "Apply")
        root.applybtn.SetToolTip(wx.ToolTip("Apply settings and regenerate G-Code"))
        root.applybtn.Bind(wx.EVT_BUTTON, root.extrude_update)
        s4.Add(root.applybtn)
