"""Lightweight painted HUD. Audio bars use actual input amplitude."""
import math
from PySide6.QtCore import Qt,QTimer,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QFont
from PySide6.QtWidgets import QWidget
from i18n import tr

class CoreViz(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumHeight(155);self.setMaximumHeight(175);self.state='waiting';self.level=0.;self.angle=0.;self.phase=0
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)
    def tick(self):
        if not self.isVisible() or self.window().isMinimized():return
        if self.state in ('listening','speaking','processing','transcribing','session','voice_loading'):self.phase+=.15;self.angle=(self.angle+2)%360
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);cx=self.width()/2;cy=self.height()/2-7;r=45
        active=self.state in ('listening','speaking','processing','transcribing','session','voice_loading');color=QColor('#c096ff' if active else '#9063d4')
        # The framing stays still at rest; motion signals real activity.
        for direction in (-1,1):
            edge=cx+direction*(r+28);far=cx+direction*min(280,self.width()*.32)
            p.setPen(QPen(QColor('#382449'),1));p.drawLine(QPointF(edge,cy),QPointF(far,cy));p.drawLine(QPointF(far,cy),QPointF(far+direction*15,cy-15));p.drawLine(QPointF(far+direction*15,cy-15),QPointF(far+direction*50,cy-15))
            p.setPen(QPen(color,2));p.drawLine(QPointF(edge+direction*20,cy),QPointF(edge+direction*42,cy))
            p.setPen(QPen(QColor('#322040'),1))
            for k in range(6):x=edge+direction*(50+k*13);p.drawLine(QPointF(x,cy+25),QPointF(x,cy+28+(k%3)*3))
        for i in range(3):
            size=r+i*10;p.setPen(QPen(QColor(134,83,191,95-i*25),1));p.drawEllipse(QPointF(cx,cy),size,size)
        p.setPen(QPen(color,2));p.drawArc(int(cx-r),int(cy-r),int(r*2),int(r*2),int(self.angle*16),245*16)
        p.setPen(QPen(QColor('#7140b2'),2));p.drawArc(int(cx-r-11),int(cy-r-11),int(r*2+22),int(r*2+22),int(-self.angle*16),150*16)
        p.setPen(QColor('#e8d9ff'));font=p.font();font.setPointSize(10);font.setBold(True);p.setFont(font);p.drawText(int(cx-42),int(cy-12),84,24,Qt.AlignmentFlag.AlignCenter,'JARVIS')
        p.setPen(QPen(color,2))
        for i in range(25):
            height=3+min(self.level,1)*22*abs(math.sin(self.phase+i*.55));x=cx-60+i*5
            p.drawLine(QPointF(x,cy+67-height/2),QPointF(x,cy+67+height/2))
        p.end()
