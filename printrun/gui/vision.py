
import wx
import cv2

import threading
import time

frame_width = 480
frame_height = 320

class VisionPane(wx.BoxSizer):
    vid = None
    root = None

    def attach_camera(self):
        self.vid = cv2.VideoCapture(0)

    def detach_camera(self):
        self.vid.release()

    def update(self, event=None):
        try:
            ret, frame = self.vid.read()
            if ret == False:
                return
            height, width = frame.shape[:2]
            scale_factor = width/frame_width if width/height > frame_width/frame_height else height/frame_height

            bmp =  wx.Bitmap.FromBuffer(width, height, frame)
            wx.Bitmap.Rescale(bmp,(int(width/scale_factor),int(height/scale_factor)))
            self.root.visionbmp.SetBitmap(bmp)
        except:
            print("Error")
            pass

    def update_continuously(self):
        while True:
            self.update()
            time.sleep(.1)

    def __init__(self, root, parentpanel = None):
        super(VisionPane, self).__init__(wx.VERTICAL)
        if not parentpanel: parentpanel = root.panel
        self.root = root

        novid = wx.Bitmap("images/novid.png", wx.BITMAP_TYPE_ANY)
        self.root.visionbmp = wx.StaticBitmap(parentpanel, wx.ID_ANY, novid, size=(frame_width,frame_height))
        self.root.visionbmp.SetScaleMode(wx.StaticBitmap.ScaleMode.Scale_AspectFit)
        self.Add(self.root.visionbmp, 1, wx.EXPAND)

        print(id(self.root.visionbmp))
        self.attach_camera()

    def __del__(self):
        self.detach_camera()
        