import burp
import threading
import random
import urlparse
import weakref
import shlex
import json
import re

from operator import attrgetter

from java.lang import Integer, String
from java.util import ArrayList
from java.awt import Color
from java.awt import BorderLayout
from java.awt import FlowLayout
from java.awt import GridBagLayout
from java.awt import GridBagConstraints
from java.awt import AlphaComposite
from java.awt import Point
from java.awt import Rectangle
from java.awt.event import ActionListener
from java.awt.geom import Rectangle2D
from java.awt.dnd import DragSourceListener
from java.awt.dnd import DragSource
from java.awt.dnd import DragGestureListener
from java.awt.dnd import DropTargetListener
from java.awt.dnd import DropTarget
from java.awt.dnd import DnDConstants
from java.awt.datatransfer import Transferable
from java.awt.datatransfer import DataFlavor
from java.awt.image import BufferedImage

from javax.swing import JScrollPane
from javax.swing import JSplitPane
from javax.swing import JTabbedPane
from javax.swing import JTable
from javax.swing import JPanel
from javax.swing import JButton
from javax.swing import JTextField
from javax.swing import JLabel
from javax.swing import JOptionPane
from javax.swing import JFrame
from javax.swing import JDialog
from javax.swing import JMenuItem
from javax.swing import BoxLayout
from javax.swing import Box
from javax.swing import BorderFactory
from javax.swing import SwingUtilities
from javax.swing import SwingConstants
from javax.swing.table import AbstractTableModel;
from javax.swing.table import TableRowSorter;
from javax.swing.table import DefaultTableCellRenderer
from javax.swing.event import RowSorterListener;
from javax.swing.event import ChangeListener;
from javax.swing.event import DocumentListener;

FILTER_HELP = """<h1>Filter Help</h1>
Searches are performed by adding filters to the list below. Only requests that match ALL the entered filters will appear in the list. Most filters have the following format:

&lt;field&gt; &lt;comparer&gt; &lt;value&gt;
        
Where &lt;field&gt; is some part of the request/response, &lt;comparer&gt; is some comparison to &lt;value&gt;. For example, if you wanted a filter that only matches requests to target.org, you could use the following filter string:
        
host is target.org

field = "host"
comparer = "is"
value = "target.org"
        
For fields that are a list of key/value pairs (headers, get params, post params, and cookies) you can use the following format:

For fields that are a list of key/value pairs (headers, get params, post params, and cookies) you can use the following format:

&lt;field&gt; &lt;comparer1&gt; &lt;value1&gt;[ &lt;comparer2&gt; &lt;value2&gt;]

This is a little more complicated. If you don't give comparer2/value2, the filter will pass any pair where the key or the value matches comparer1 and value1. If you do give comparer2/value2, the key must match comparer1/value1 and the value must match comparer2/value2 For example:

Filter A:
    cookie contains Session

Filter B:
    cookie contains Session contains 456

Filter C:
    inv cookie contains Ultra

Cookie: SuperSession=abc123
Matches A and C but not B

Cookie: UltraSession=abc123456
Matches both A and B but not C

<h1>List of string fields</h1>
all (all) - Anywhere in the request, response, or a websocket message
reqbody (reqbody, reqbd, qbd, qdata, qdt) - The body of the request
rspbody (rspbody, rspbd, sbd, sdata, sdt) - The body of the response
body (body, bd, data, dt) - The body in either the request or the response
method (method, verb, vb) - The request method (GET, POST, etc)
host (host, domain, hs, dm) - The host that the request was sent to
path (path, pt) - The path of the request
url (url) - The full URL of the request
statuscode (statuscode, sc) - The status code of the response (200, 404, etc)
tool (tool) - The tool this request came from

<h1>List of key/value fields</h1>
reqheader (reqheader, reqhd, qhd) - A header in the request
rspheader (rspheader, rsphd, shd) - A header in the response
header (header, hd) - A header in the request or the response
urlparam (urlparam, uparam) - A URL parameter of the request
postparam (postparam, pparam) - A post parameter of the request
param (param, pm) - Any request parameter (body, json, multipart attribute, url, xml, xml attribute)
rspcookie (rspcookie, rspck, sck) - A cookie set by the response
reqcookie (reqcookie, reqck, qck) - A cookie submitted by the request
cookie (cookie, ck) - A cookie sent by the request or a cookie set by the response
        
<h1>List of comparers</h1>
is (is) - Exact string match
iscs (iscs) - Same as the "is" comparer but case sensitive
contains (contains, ct) - A contain B is true if B is a substring of A
containscs (containscs, ctcs) - Same as the "contains" comparer but case sensitive
containsr (containsr, ctr) - A containr B is true if A matches regexp B
leneq (leneq) - A Leq B if A's length equals B (B must be a number)
lengt (lengt) - A Lgt B if A's length is greater than B (B must be a number)
lenlt (lenlt) - A Llt B if A's length is less than B (B must be a number)
        
<h1>Special form filters</h1>
invert (invert, inv) - Inverts the following filter. Will match anything that does NOT match the following filter
"""

class Event(object):
    def __init__(self):
        self._subscribers = []

    def add_listener(self, f):
        #self._subscribers.append(weakref.ref(f, callback=lambda: self.remove_listener(f)))
        self._subscribers.append(f)

    def remove_listener(self, f):
        if f in self._subscribers:
            self._subscribers.remove(f)

    def invoke(self, *args, **kwargs):
        for f in self._subscribers:
            f(*args, **kwargs)

class DnDTabbedPane(JTabbedPane):
    class GhostGlassPane(JPanel):

        def __init__(self):
            JPanel.__init__(self)
            self.location = Point(0, 0)
            self.draggingGhost = None

            self.setOpaque(False)
            self.composite = AlphaComposite.getInstance(AlphaComposite.SRC_OVER, 0.5)

        def setImage(self, draggingGhost):
            self.draggingGhost = draggingGhost

        def setPoint(self, location):
            self.location = location

        def paintComponent(self, g):
            if self.draggingGhost is None:
                return
            g.setComposite(composite)
            xx = location.getX() - (draggingGhost.getWidth(self)/2)
            yy = location.getY() - (draggingGhost.getHeight(self)/2)
            g.drawImage(draggingGhost, xx, yy, None)

    class _SourceListener(DragSourceListener):
        def __init__(self, dndPane):
            JTabbedPane.__init__(self)
            self.dndPane = dndPane

        def dragEnter(self, e):
            e.getDragSourceContext().setCursor(DragSource.DefaultMoveDrop)

        def dragExit(self, e):
            e.getDragSourceContext().setCursor(DragSource.DefaultMoveNoDrop)
            self.dndPane.lineRect.setRect(0, 0, 0, 0)
            self.dndPane.glassPane.setPoint(Point(-1000, -1000))
            self.dndPane.glassPane.repaint()

        def dragOver(self, e):
            tabPt = e.getLocation()
            SwingUtilities.convertPointFromScreen(tabPt, self.dndPane)
            glassPt = e.getLocation()
            SwingUtilities.convertPointFromScreen(glassPt, self.dndPane.glassPane)
            targetIdx = self.dndPane.getTargetTabIndex(glassPt)
            if self.dndPane.getTabAreaBound().contains(tabPt) and targetIdx >= 0 and targetIdx != self.dndPane.dragTabIndex and targetIdx != self.dndPane.dragTabIndex+1:
                e.getDragSourceContext().setCursor(DragSource.DefaultMoveDrop)
            else:
                e.getDragSourceContext().setCursor(DragSource.DefaultMoveNoDrop)

        def dragDropEnd(self, e):
            self.dndPane.lineRect.setRect(0, 0, 0, 0)
            self.dndPane.dragTabIndex = -1
            if (self.dndPane.hasGhost):
                self.dndPane.glassPane.setVisible(False)
                self.dndPane.glassPane.setImage(None)

        def dropActionChanged(self, e):
            pass

    class _Transferable(Transferable):
        def __init__(self, dndPane):
            Transferable.__init__(self)
            self.dndPane = dndPane
            self.FLAVOR = DataFlavor(DataFlavor.javaJVMLocalObjectMimeType, self.dndPane.NAME)

        def getTransferData(self, flavor):
            return self.dndPane

        def getTransferDataFlavors(self):
            return [self.FLAVOR]

        def isDataFlavorSupported(self, flavor):
            return flavor.getHumanPresentableName() == self.dndPane.NAME

    class _DragGestureListener(DragGestureListener):
        def __init__(self, dndPane):
            DragGestureListener.__init__(self)
            self.dndPane = dndPane

        def dragGestureRecognized(self, e):
            tabPt = e.getDragOrigin()
            self.dndPane.dragTabIndex = self.dndPane.indexAtLocation(tabPt.x, tabPt.y)
            if self.dndPane.dragTabIndex < 0:
                return
            self.dndPane.initGlassPane(e.getComponent(), e.getDragOrigin())
            #try:
            e.startDrag(DragSource.DefaultMoveDrop, self.dndPane.t, self.dndPane.dsl)
            #except:
            #    print(e)

    class CDropTargetListener(DropTargetListener):
        def __init__(self, dndPane):
            DragGestureListener.__init__(self)
            self.dndPane = dndPane

        def dragEnter(self, e):
            if self.isDragAcceptable(e):
                e.acceptDrag(e.getDropAction())
            else:
                e.rejectDrag()

        def dragExit(self, e):
            pass

        def dropActionChanged(self, e):
            pass

        def dragOver(self, e):
            if self.dndPane.getTabPlacement() == JTabbedPane.TOP or getTabPlacement() == JTabbedPane.BOTTOM:
                self.dndPane.initTargetLeftRightLine(self.dndPane.getTargetTabIndex(e.getLocation()))
            else:
                self.dndPane.initTargetTopBottomLine(self.dndPane.getTargetTabIndex(e.getLocation()))
            self.dndPane.repaint()
            if self.dndPane.hasGhost:
                self.dndPane.glassPane.setPoint(e.getLocation())
                self.dndPane.glassPane.repaint()

        def drop(self, e):
            if self.isDropAcceptable(e):
                target_ind = self.dndPane.getTargetTabIndex(e.getLocation())
                if self.dndPane.allowLast or target_ind < self.dndPane.getTabCount():
                    self.dndPane.convertTab(self.dndPane.dragTabIndex, self.dndPane.getTargetTabIndex(e.getLocation()))
                e.dropComplete(True)
            else:
                e.dropComplete(False)

            self.dndPane.repaint()

        def isDragAcceptable(self, e):
            t = e.getTransferable()
            if t is None:
                return False
            f = e.getCurrentDataFlavors()
            if t.isDataFlavorSupported(f[0]) and self.dndPane.dragTabIndex >= 0:
                return True
            return False

        def isDropAcceptable(self, e):
            t = e.getTransferable()
            if t is None:
                return False
            f = t.getTransferDataFlavors()
            if t.isDataFlavorSupported(f[0]) and self.dndPane.dragTabIndex >= 0:
                return True
            return False

    def __init__(self):
        JTabbedPane.__init__(self)

        self.LINEWIDTH = 3
        self.NAME = "test"
        self.glassPane = DnDTabbedPane.GhostGlassPane()
        self.lineRect = Rectangle2D.Double()
        self.lineColor = Color(0, 100, 255)
        self.dragTabIndex = -1
        self.hasGhost = True
        self.allowLast = True
        self.no_add_tabs = False

        self.dsl = DnDTabbedPane._SourceListener(self)
        self.t = DnDTabbedPane._Transferable(self)
        self.dgl = DnDTabbedPane._DragGestureListener(self)

        self.dropTarget = DropTarget(self.glassPane, DnDConstants.ACTION_COPY_OR_MOVE, DnDTabbedPane.CDropTargetListener(self), True)
        self.dragSource = DragSource().createDefaultDragGestureRecognizer(self, DnDConstants.ACTION_COPY_OR_MOVE, self.dgl)

    def getTargetTabIndex(self, glassPt):
        # checked glassPt instead of tabPt because it worked for some reason
        tabPt = SwingUtilities.convertPoint(self.glassPane, glassPt, self)
        isTB = self.getTabPlacement() == JTabbedPane.TOP or self.getTabPlacement() == JTabbedPane.BOTTOM
        for i in range(self.getTabCount()):
            r = self.getBoundsAt(i)
            if isTB:
                r.setRect(r.x - r.width/2, r.y, r.width, r.height)
            else:
                r.setRect(r.x, r.y-r.height/2, r.width, r.height)
            #if r.contains(tabPt):
            if r.contains(glassPt):
                return i
        r = self.getBoundsAt(self.getTabCount()-1)
        if isTB:
            r.setRect(r.x + r.width/2, r.y, r.width, r.height)
        else:
            r.setRect(r.x, r.y + r.height/2, r.width, r.height)

        #if r.contains(tabPt):
        if r.contains(glassPt):
            return self.getTabCount()
        return -1

    def convertTab(self, prev, nxt):
        if nxt < 0 or prev == nxt:
            return
        prevNoAdd = self.no_add_tabs
        self.no_add_tabs = True
        comp = self.getComponentAt(prev)
        stri = self.getTitleAt(prev)
        if nxt == self.getTabCount():
            self.remove(prev)
            self.addTab(stri, comp)
            self.setSelectedIndex(self.getTabCount()-1)
        elif prev > nxt:
            self.remove(prev)
            self.insertTab(stri, None, comp, None, nxt)
            self.setSelectedIndex(nxt)
        else:
            self.remove(prev)
            self.insertTab(stri, None, comp, None, nxt-1)
            self.setSelectedIndex(nxt-1)
        self.no_add_tabs = prevNoAdd
        self.tabsConverted()

    def tabsConverted(self):
        pass

    def initTargetLeftRightLine(self, nxt):
        if nxt < 0 or self.dragTabIndex == nxt or nxt - self.dragTabIndex == 1:
            self.lineRect.setRect(0, 0, 0, 0)
        elif nxt == self.getTabCount():
            rect = self.getBoundsAt(self.getTabCount()-1)
            self.lineRect.setRect(rect.x + rect.width - self.LINEWIDTH/2, rect.y, self.LINEWIDTH, rect.height)
        elif nxt == 0:
            rect = self.getBoundsAt(0)
            self.lineRect.setRect(-self.LINEWIDTH/2, rect.y, self.LINEWIDTH, rect.height)
        else:
            rect = self.getBoundsAt(nxt-1)
            self.lineRect.setRect(rect.x + rect.width - self.LINEWIDTH/2, rect.y, self.LINEWIDTH, rect.height)

    def initTargetTopBottomLine(self, nxt):
        if nxt < 0 or self.dragTabIndex == nxt or nxt - self.dragTabIndex == 1:
            self.lineRect.setRect(0, 0, 0, 0)
        elif nxt == self.getTabCount():
            rect = self.getBoundsAt(self.getTabCount()-1)
            self.lineRect.setRect(rect.x, rect.y + rect.height - self.LINEWIDTH/2, rect.width, self.LINEWIDTH)
        elif nxt == 0:
            rect = self.getBoundsAt(0)
            self.lineRect.setRect(rect.x, -self.LINEWIDTH/2, rect.width, self.LINEWIDTH)
        else:
            rect = self.getBoundsAt(nxt - 1)
            self.lineRect.setRect(rect.x, rect.y + rect.height - self.LINEWIDTH/2, rect.width, self.LINEWIDTH)

    def initGlassPane(self, c, tabPt):
        self.getRootPane().setGlassPane(self.glassPane)
        if self.hasGhost:
            rect = self.getBoundsAt(self.dragTabIndex)
            image = BufferedImage(c.getWidth(), c.getHeight(), BufferedImage.TYPE_INT_ARGB)
            g = image.getGraphics()
            c.paint(g)
            image = image.getSubimage(rect.x, rect.y, rect.width, rect.height)
        glassPt = SwingUtilities.convertPoint(c, tabPt, self.glassPane)
        self.glassPane.setPoint(glassPt)
        self.glassPane.setVisible(True)

    def getTabAreaBound(self):
        lastTab = self.getUI().getTabBounds(self, self.getTabCount()-1)
        return Rectangle(0, 0, self.getWidth(), lastTab.y+lastTab.height)

    #def paintComponent(self, g):
    #    super(JTabbedPane, self).paintComponent(g)
    #    if self.dragTabIndex >= 0:
    #        g.setPaint(self.lineColor)
    #        g.fill(self.lineRect)

class CustomRequestResponse(burp.IHttpRequestResponse):
    # Every call in the code to getRequest or getResponse must be followed by
    # callbacks.analyzeRequest or analyze Response OR
    # FloydsHelpers.jb2ps OR
    # another operation such as len()

    def __init__(self, comment, highlight, service, request, response):
        self.com = comment
        self.high = highlight
        self.setHttpService(service)
        self.setRequest(request)
        self.setResponse(response)

    def getComment(self):
        return self.com

    def getHighlight(self):
        return self.high

    def getHttpService(self):
        return self.serv

    def getRequest(self):
        return self.req

    def getResponse(self):
        return self.resp

    def setComment(self, comment):
        self.com = comment

    def setHighlight(self, color):
        self.high = color

    def setHttpService(self, httpService):
        if isinstance(httpService, str):
            self.serv = CustomHttpService(httpService)
        else:
            self.serv = httpService

    def setRequest(self, message):
        if isinstance(message, str):
            self.req = ps2jb(message)
        else:
            self.req = message

    def setResponse(self, message):
        if isinstance(message, str):
            self.resp = ps2jb(message)
        else:
            self.resp = message

    def serialize(self):
        return self.com, self.high, CustomHttpService.to_url(self.serv), jb2ps(self.req), jb2ps(self.resp)

    def deserialize(self, serialized_object):
        self.com, self.high, service_url, self.req, self.resp = serialized_object
        self.req = ps2jb(self.req)
        self.resp = ps2jb(self.resp)
        self.serv = CustomHttpService(service_url)

class CustomHttpService(burp.IHttpService):
    def __init__(self, url):
        x = urlparse.urlparse(url)
        if x.scheme in ("http", "https"):
            self._protocol = x.scheme
        else:
            raise ValueError()
        self._host = x.hostname
        if not x.hostname:
            self._host = ""
        self._port = None
        if x.port:
             self._port = int(x.port)
        if not self._port:
            if self._protocol == "http":
                self._port = 80
            elif self._protocol == "https":
                self._port = 443

    def getHost(self):
        return self._host

    def getPort(self):
        return self._port

    def getProtocol(self):
        return self._protocol

    def __str__(self):
        return CustomHttpService.to_url(self)

    @staticmethod
    def to_url(service):
        a = u2s(service.getProtocol()) + "://" + u2s(service.getHost())
        if service.getPort():
            a += ":" + str(service.getPort())
        return a + "/"

class SavedRequest(object):
    REQUEST_HISTORY_HOST = "birch-request-history"
    
    def __init__(self, extender, reqrsp=None, msg_id=-1, tool="None", _data_reqrsp=None):
        self.extender = extender
        
        if _data_reqrsp is not None:
            self._load_from_data_reqrsp(_data_reqrsp)
        else:
            self.reqrsp = reqrsp
            self.msg_id = msg_id
            self.tool = tool

    def save_to_history(self):
        # create a new history entry for this message set
        self.extender.callbacks.addToSiteMap(self._create_data_reqrsp())

    def _create_data_reqrsp(self):
        fullreq = jb2ps(self.reqrsp.getRequest())
        req_dat = "GET /{msgid}/ HTTP/1.1\r\nContent-Length: {contentlength}\r\n\r\n{data}".format(msgid=self.msg_id, contentlength=len(fullreq), data=fullreq)
        svc = self.reqrsp.getHttpService()

        rsp = self.reqrsp.getResponse()
        fullrsp = None
        rsp_dat = None
        if rsp is not None:
            fullrsp = jb2ps(rsp)
            rsp_dat = "HTTP/1.1 200 OK\r\nContent-Length: {contentlength}\r\n\r\n{data}".format(contentlength=len(fullrsp), data=fullrsp)

        metadata = {
            'h': svc.getHost(), # host
            'p': svc.getPort(), # port
            'r': svc.getProtocol(), # protocol
            't': self.tool, # tool
            'i': self.msg_id, # message id
            }
        metadata_str = json.dumps(metadata, separators=(',', ':'))

        return CustomRequestResponse(metadata_str, '', CustomHttpService('http://'+self.REQUEST_HISTORY_HOST+"/"+str(self.msg_id)+"/"), req_dat, rsp_dat)

    def _load_from_data_reqrsp(self, data_reqrsp):
        comment = data_reqrsp.getComment()
        meta = {}
        if comment:
            meta = json.loads(comment)
        host = meta.get('h', '127.0.0.1')
        port = meta.get('p', 80)
        protocol = meta.get('r', 'http')
        self.msg_id = meta.get('i', -1)
        svc = CustomHttpService(protocol+"://"+host+":"+str(port))

        reqinfo = self.extender.helpers.analyzeRequest(data_reqrsp)
        fullreq = jb2ps(data_reqrsp.getRequest()[reqinfo.getBodyOffset():])

        rsp = data_reqrsp.getResponse()
        fullrsp = None
        if rsp is not None:
            rspinfo = self.extender.helpers.analyzeResponse(rsp)
            fullrsp = rsp[rspinfo.getBodyOffset():]

        self.reqrsp = CustomRequestResponse('', '', svc, fullreq, fullrsp)
        self.tool = meta.get('t', 'None')

    @classmethod
    def get_saved_requests(cls, extender):
        msgs = extender.callbacks.getSiteMap("http://"+cls.REQUEST_HISTORY_HOST+"/")
        ret = []
        for msg in msgs:
            reqinfo = extender.helpers.analyzeRequest(msg)
            if reqinfo.getBodyOffset() == len(msg.getRequest()):
                # burp adds hidden, empty entries when you add a message to the map. Skip those
                continue
            saved_reqrsp = SavedRequest(extender, _data_reqrsp=msg)
            ret.append(saved_reqrsp)
        return ret
    

class BurpExtender(burp.IBurpExtender, burp.IExtensionStateListener, burp.IHttpListener, burp.ITab, burp.IContextMenuFactory):
    SETTINGS_REQ_HOST = "birch-settings"
    ALLOWED_TOOLS = ["proxy", "repeater"]

    def __init__(self):
        self.all_request_entries = []

    def registerExtenderCallbacks(self, callbacks):
        self._lock = threading.Lock()

        self.callbacks = callbacks
        self.helpers = callbacks.getHelpers()
        self.new_message_added = Event()
        self.message_updated = Event()

        # metadata
        self.callbacks.setExtensionName("Birch")

        # setup
        RequestHistoryModel.populate_history(self)

        # ui
        self._search_panes = TabbedBirchPane(self)
        self.load_settings()

        # callbacks
        self.callbacks.registerExtensionStateListener(self)
        self.callbacks.registerHttpListener(self)
        self.callbacks.registerContextMenuFactory(self)
        callbacks.addSuiteTab(self)

        print("loaded")

    def processHttpMessage(self, toolFlag, messageIsRequest, messageInfo):
        with self._lock:
            tool_name = self.callbacks.getToolName(toolFlag)
            if tool_name.lower() in self.ALLOWED_TOOLS:
                saved = RequestHistoryModel.add_entry(self, messageInfo, tool=tool_name, update=(not messageIsRequest))

                if tool_name.lower() != 'proxy':
                    sr = SavedRequest(self, reqrsp=messageInfo, msg_id=saved.entry_id, tool=tool_name)
                    sr.save_to_history()

    def extensionUnloaded(self):
        self.save_settings()
        print("unloaded")

    def getTabCaption(self):
        return "Birch"

    def getUiComponent(self):
        return self._search_panes

    def createMenuItems(self, invocation):
        self.context = invocation
        menuList = ArrayList()

        menuList.add(JMenuItem("Add to Birch history", actionPerformed=self.handle_send_to_birch))

        return menuList

    def _create_settings_reqrsp(self, key, val):
        req = "GET /" + key + "/ HTTP/1.1\r\n\r\nThis request is used by the Birch extension to store per-project data. No, the Burp extender API does not provide a way to do this."
        rsp = "HTTP/1.1 200 OK\r\n"
        return CustomRequestResponse(val, '', CustomHttpService('http://'+self.SETTINGS_REQ_HOST+"/"), req, rsp)

    def _get_setting_request(self, key):
        for reqrsp in self.callbacks.getSiteMap("http://"+self.SETTINGS_REQ_HOST+"/"+key+"/"):
            return reqrsp
        return None

    def load_project_setting(self, key):
        getfrom = self._get_setting_request(key)
        if getfrom == None:
            getfrom = self._create_settings_reqrsp(key, "")
            self.callbacks.addToSiteMap(getfrom)
        return getfrom.getComment()

    def save_project_setting(self, key, value):
        reqrsp = self._create_settings_reqrsp(key, value)
        self.callbacks.addToSiteMap(reqrsp)

    def save_settings(self):
        s = self._search_panes.serialize()
        srz = json.dumps(s, separators=(',', ':'))
        self.save_project_setting("data", srz)

    def load_settings(self):
        srzd = self.load_project_setting("data")
        if srzd and len(srzd) > 0:
            try:
                s = json.loads(srzd)
                self._search_panes.deserialize(s)
                print("Successfully loaded settings")
            except Exception as e:
                print("Failed to load settings")
                print(e)

    def handle_send_to_birch(self, event):
        msgs = self.context.getSelectedMessages()
        for msg in msgs:
            tool = "Manual"
            saved = RequestHistoryModel.add_entry(self, msg, tool=tool)
            sr = SavedRequest(self, reqrsp=msg, msg_id=saved.entry_id, tool=tool)
            sr.save_to_history()

class TabbedBirchPane(DnDTabbedPane, ChangeListener):
    class _TabCloseHandler(ActionListener):
        def __init__(self, tabPane, i):
            self._ind = i
            self._tabPane = tabPane

        def actionPerformed(self, e):
            self._tabPane.add_tab = True
            idx = self._tabPane.getSelectedIndex()
            if idx == self._ind:
                idx -= 1
                if idx < 0:
                    idx = 0
                self._tabPane.setSelectedIndex(idx)
            self._tabPane.getComponentAt(self._ind).on_close()
            self._tabPane.remove(self._ind)
            self._tabPane.update_titles()
            self._tabPane.add_tab = False

    def __init__(self, extender):
        DnDTabbedPane.__init__(self)
        self._extender = extender
        self.no_add_tabs = False
        self.next_tab = 1
        self.allowLast = False

        self.addChangeListener(self)

        self.addTab("+", None)

    def add_search_tab(self, title="", select=False):
        if title == "":
            title = self.generate_tab_name()
        tab_index = self.getTabCount()-1
        contents_pane = BirchSearchPane(self._extender, self, tab_index, title)
        self.insertTab(title, None, contents_pane, "", tab_index)
        self.set_tab_title(tab_index, title)
        if select:
            self.setSelectedIndex(self.getTabCount()-2)
        return contents_pane

    def set_tab_title(self, tab_index, title):
        self.setTitleAt(tab_index, title)
        tabPanel = JPanel(GridBagLayout())
        titleLabel = JLabel(" " + title+ "   ")
        closeButton = JButton("X")
        closeButton.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0))

        gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.weightx = 1

        tabPanel.add(titleLabel, gbc)
        gbc.gridx += 1
        gbc.weightx = 0
        tabPanel.add(closeButton, gbc)
        self.setTabComponentAt(tab_index, tabPanel)
        closeButton.addActionListener(TabbedBirchPane._TabCloseHandler(self, tab_index))

    def tabsConverted(self):
        self.update_titles()

    def generate_tab_name(self):
        found = True
        name = str(self.next_tab)
        while found:
            found = False
            name = str(self.next_tab)
            self.next_tab += 1
            for i in range(self.getTabCount()-1):
                if self.getTitleAt(i) == name:
                    found = True
                    break
        return name

    def update_titles(self):
        for i in range(self.getTabCount()-1):
            self.set_tab_title(i, self.getTitleAt(i))
            self.getComponentAt(i).tab_index = i

    def duplicate_tab(self, tab_index, select_new_tab=False):
        prev_tab = self.getComponentAt(tab_index)
        srzd = prev_tab.serialize()
        new_tab = self.add_search_tab(select=True)
        new_tab.deserialize(srzd)

    def stateChanged(self, e):
        if self.no_add_tabs:
            return
        self.no_add_tabs = True
        if self.getSelectedIndex() == self.getTabCount()-1:
            self.add_search_tab()
            self.setSelectedIndex(self.getTabCount()-2)
        self.no_add_tabs = False

    def serialize(self):
        tabs = []
        for i in range(self.getTabCount()-1):
            comp = self.getComponentAt(i)
            tabs.append(comp.serialize())
        return {
            't': tabs,
        }

    def deserialize(self, s):
        self.no_add_tabs = True
        for i in range(self.getTabCount()-1):
            self.remove(0)
        self.next_tab = 1

        if 't' in s and len(s['t']) > 0:
            for t in s['t']:
                self.add_search_tab().deserialize(t)
        else:
            self.add_search_tab()
        self.setSelectedIndex(0)
        self.no_add_tabs = False

class BirchSearchPane(JPanel, burp.IMessageEditorController):
    class _TabTitleHandler(ActionListener, DocumentListener):
        def __init__(self, search_pane, text_box):
            self._search_pane = search_pane
            self._text_box = text_box

        def _do_update(self):
            s = self._text_box.getText()
            if s == "":
                return
                #s = self._tabbed_pane.generate_tab_name()
            self._search_pane.set_tab_title(s, _update_text_box=False)

        def actionPerformed(self, e):
            self._do_update()
            self._text_box.setFocusable(False)
            self._text_box.setFocusable(True)

        def changedUpdate(self, e):
            self._do_update()

        def insertUpdate(self, e):
            self._do_update()

        def removeUpdate(self, e):
            self._do_update()

    class _DuplicateTabHandler(ActionListener):
        def __init__(self, tabbed_pane, search_pane):
            self._tabbed_pane = tabbed_pane
            self._search_pane = search_pane
        
        def actionPerformed(self, e):
            self._tabbed_pane.duplicate_tab(self._search_pane.tab_index)

    def __init__(self, extender, tab_pane, tab_index, tab_name):
        JPanel.__init__(self)
        self._extender = extender
        self._tab_pane = tab_pane
        self._currentlyDisplayedItem = None
        self.tab_index = tab_index
        self.filters_changed = Event()

        # main split pane
        self.setLayout(BorderLayout())
        history_msgs_split_pane = JSplitPane(JSplitPane.VERTICAL_SPLIT)
        history_msgs_split_pane.setResizeWeight(0.3)
        self.add(history_msgs_split_pane, BorderLayout.CENTER)

        # toolbar
        tb_pane = JPanel(FlowLayout(FlowLayout.LEADING))
        tb_pane.add(JLabel("Tab Name:"))
        self.tab_title_field = JTextField(10)
        self.tab_title_field.setText(tab_name)
        title_listener = BirchSearchPane._TabTitleHandler(self, self.tab_title_field)
        self.tab_title_field.addActionListener(title_listener)
        self.tab_title_field.getDocument().addDocumentListener(title_listener)
        tb_pane.add(self.tab_title_field)
        tb_pane.add(Box.createHorizontalStrut(5))
        dup_but = JButton("Duplicate Tab")
        dup_but.addActionListener(BirchSearchPane._DuplicateTabHandler(self._tab_pane, self))
        tb_pane.add(dup_but)
        self.add(tb_pane, BorderLayout.PAGE_START)

        # message viewer pane
        self._request_viewer = self._extender.callbacks.createMessageEditor(self, False)
        self._response_viewer = self._extender.callbacks.createMessageEditor(self, False)
        message_viewer = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)
        message_viewer.setResizeWeight(0.5)
        message_viewer.setLeftComponent(self._request_viewer.getComponent())
        message_viewer.setRightComponent(self._response_viewer.getComponent())
        history_msgs_split_pane.setRightComponent(message_viewer)

        # search entry pane
        self._search_entry = BirchSearchEntry(self._extender, self)

        # history pane
        self._history_model = RequestHistoryModel(self._extender, self)
        self._history_table = RequestTable(self._history_model, self)

        table_search_split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)
        table_search_split.setLeftComponent(JScrollPane(self._history_table))
        table_search_split.setRightComponent(self._search_entry)
        table_search_split.setResizeWeight(0.6)
        history_msgs_split_pane.setLeftComponent(table_search_split)

    def serialize(self):
        return {
            't': self.get_tab_title(),
            'f': self._search_entry.serialize_filters(),
        }

    def deserialize(self, s):
        if 'f' in s:
            self._search_entry.deserialize_filters(s['f'])
        if 't' in s:
            self.set_tab_title(s['t'])
        
    def get_tab_title(self):
        return self._tab_pane.getTitleAt(self.tab_index)

    def set_tab_title(self, s, _update_text_box=True):
        self._tab_pane.set_tab_title(self.tab_index, s)
        if _update_text_box:
            self.tab_title_field.setText(s)
        
    def check_model_entry(self, entry):
        return self._search_entry.check_model_entry(entry)

    def set_displayed_message(self, reqrsp):
        self._currentlyDisplayedItem = reqrsp
        self._request_viewer.setMessage(reqrsp.getRequest(), True)
        self._response_viewer.setMessage(reqrsp.getResponse(), False)

    def on_close(self):
        self._history_model.unsubscribe_from_events()

    # IMessageEditorController impl
    def getHttpService(self):
        if self._currentlyDisplayedItem == None:
            return None
        return self._currentlyDisplayedItem.getHttpService()

    def getRequest(self):
        if self._currentlyDisplayedItem == None:
            return None
        return self._currentlyDisplayedItem.getRequest()

    def getResponse(self):
        if self._currentlyDisplayedItem == None:
            return None
        return self._currentlyDisplayedItem.getResponse()

class RequestHistoryModelEntry(object):
    def __init__(self, extender, reqrsp, tool="None", entry_id=-1):
        self._extender = extender
        self.tool = tool
        self.entry_id = entry_id

        self.set_request_response(reqrsp)

    def set_request_response(self, reqrsp):
        self._message_info_persisted = self._extender.callbacks.saveBuffersToTempFiles(reqrsp)
        self.request_info = self._extender.helpers.analyzeRequest(reqrsp)
        rsp = reqrsp.getResponse()
        if rsp is None:
            self.response_info = None
            self.status = ""
            self.length = 0
            self.mime = ""
            self.incomplete = True
        else:
            self.response_info = self._extender.helpers.analyzeResponse(rsp)
            self.status = str(self.response_info.getStatusCode())
            self.length = len(reqrsp.getResponse()) - self.response_info.getBodyOffset()
            self.mime = self.response_info.getStatedMimeType()
            self.incomplete = False

        self.method = self.request_info.getMethod()
        self.comment = reqrsp.getComment() or ""

        url = self.request_info.getUrl()
        self.path = url.getPath()
        self.full_url = str(url)

        host = reqrsp.getHttpService().getHost()
        port = reqrsp.getHttpService().getPort()
        scheme = reqrsp.getHttpService().getProtocol()
        is_ssl = scheme[-1] == "s"

        if (is_ssl and port != 443) or (not is_ssl and port != 80):
            self.host = "%s://%s:%s" % (scheme, host, port)
        else:
            self.host = "%s://%s" % (scheme, host)

    def get_request_response(self):
        return self._message_info_persisted

class RequestHistoryModel(AbstractTableModel):
    all_entries = []
    
    def __init__(self, extender, search_pane):
        self._extender = extender
        self._all_entries = []
        self._entries = []
        self._search_pane = search_pane

        self.subscribe_to_events()
        self.filters_changed()

    def subscribe_to_events(self):
        self._search_pane.filters_changed.add_listener(self.filters_changed)
        self._extender.new_message_added.add_listener(self.on_new_entry)
        self._extender.message_updated.add_listener(self.on_entry_updated)

    def unsubscribe_from_events(self):
        self._search_pane.filters_changed.remove_listener(self.filters_changed)
        self._extender.new_message_added.remove_listener(self.on_new_entry)
        self._extender.message_updated.remove_listener(self.on_entry_updated)

    @classmethod
    def populate_history(cls, extender):
        proxy_msgs = extender.callbacks.getProxyHistory()
        saved_msgs = SavedRequest.get_saved_requests(extender)
        saved_msgs = sorted(saved_msgs, key=attrgetter('msg_id'))

        saved_ind = 0
        proxy_ind = 0
        for proxy_ind in range(len(proxy_msgs)):
            while saved_ind < len(saved_msgs) and saved_msgs[saved_ind].msg_id <= len(cls.all_entries):
                saved = saved_msgs[saved_ind]
                cls.add_entry(extender, saved.reqrsp, saved.tool)
                saved_ind += 1
            cls.add_entry(extender, proxy_msgs[proxy_ind], tool="Proxy")

        while saved_ind < len(saved_msgs):
            saved = saved_msgs[saved_ind]
            cls.add_entry(extender, saved.reqrsp, saved.tool)
            saved_ind += 1

    @classmethod
    def add_entry(cls, extender, reqrsp, tool="None", update=False):
        if update:
            request_info = extender.helpers.analyzeRequest(reqrsp)
            fullurl = str(request_info.getUrl())
            for entry in cls.all_entries:
                if not entry.incomplete:
                    continue
                if fullurl == entry.full_url and reqrsp.getRequest() == entry.get_request_response().getRequest():
                    entry.set_request_response(reqrsp)
                    extender.message_updated.invoke(entry)
                    return entry
        new_entry = RequestHistoryModelEntry(extender, reqrsp, tool=tool, entry_id=len(cls.all_entries)+1)
        cls.all_entries.append(new_entry)
        extender.new_message_added.invoke(new_entry)
        return new_entry

    def filters_changed(self):
        self._entries = []
        for e in RequestHistoryModel.all_entries:
            reqrsp = e.get_request_response()
            req_info = self._extender.helpers.analyzeRequest(reqrsp)
            rsp = reqrsp.getResponse()
            if rsp is None:
                rsp_info = None
            else:
                rsp_info = self._extender.helpers.analyzeResponse(rsp)
            if self._search_pane.check_model_entry(e):
                self._entries.append(e)
        self.fireTableDataChanged()

    def on_new_entry(self, new_entry):
        if self.check_entry(new_entry):
            row_ind = len(self._entries)
            self._entries.append(new_entry)
            self.fireTableRowsInserted(row_ind, row_ind)

    def on_entry_updated(self, entry):
        entry_exists = False
        entry_ind = 0
        for e in self._entries:
            if e == entry:
                entry_exists = True
                break
            entry_ind += 1

        entry_matches = self.check_entry(entry)

        if entry_exists and entry_matches:
            self.fireTableRowsUpdated(entry_ind, entry_ind)

        if entry_exists and not entry_matches:
            del self._entries[entry_ind]
            self.fireTableRowsDeleted(entry_ind, entry_ind)

        if not entry_exists and entry_matches:
            row_ind = len(self._entries)
            self._entries.append(entry)
            self.fireTableRowsInserted(row_ind, row_ind)

    def check_entry(self, entry):
        return self._search_pane.check_model_entry(entry)

    # Model implementation
    def getRowCount(self):
        return len(self._entries)

    def getColumnCount(self):
        return 9

    def getColumnName(self, columnIndex):
        if columnIndex == 0:
            return "#"
        elif columnIndex == 1:
            return "Tool"
        elif columnIndex == 2:
            return "Host"
        elif columnIndex == 3:
            return "Method"
        elif columnIndex == 4:
            return "URL"
        elif columnIndex == 5:
            return "Status"
        elif columnIndex == 6:
            return "Length"
        elif columnIndex == 7:
            return "MIME type"
        elif columnIndex == 8:
            return "Comment"
        return ""

    def getColumnClass(self, columnIndex):
        if columnIndex == 0: # #
            return Integer(0).getClass()
        if columnIndex == 5: # status
            return Integer(0).getClass()
        if columnIndex == 6: # length
            return Integer(0).getClass()
        return String("").getClass()

    def getPreferredWidth(self, columnIndex):
        if columnIndex == 0:
            return 40
        elif columnIndex == 1:
            return 60
        elif columnIndex == 2:
            return 150
        elif columnIndex == 3:
            return 55
        elif columnIndex == 4:
            return 430
        elif columnIndex == 5:
            return 55
        elif columnIndex == 6:
            return 55
        elif columnIndex == 7:
            return 55
        elif columnIndex == 8:
            return 160
        return 20

    def getValueAt(self, rowIndex, columnIndex):
        entry = self._entries[rowIndex]
        ret = ""
        if columnIndex == 0:
            ret = entry.entry_id
        elif columnIndex == 1:
            ret = entry.tool
        elif columnIndex == 2:
            ret = entry.host
        elif columnIndex == 3:
            ret = entry.method
        elif columnIndex == 4:
            ret = entry.path
        elif columnIndex == 5:
            ret = entry.status
        elif columnIndex == 6:
            ret = entry.length
        elif columnIndex == 7:
            ret = entry.mime
        elif columnIndex == 8:
            ret = entry.comment

        return ret

class RequestTableCellRenderer(DefaultTableCellRenderer):
    _str_colorcache = {}
    _was_dark_mode = False
    
    def method_color(self, table, method, dark=False):
        default_col = table.getBackground()
        lightcols = {
            'get': Color(240, 240, 255),
            'post': Color(255, 255, 230),
            'put': Color(255, 240, 240),
            'patch': Color(240, 255, 240),
            'delete': Color(255, 240, 255),
            }

        darkcols = {
            'get': Color(90, 90, 115),
            'post': Color(115, 115, 80),
            'put': Color(115, 90, 90),
            'patch': Color(90, 115, 90),
            'delete': Color(115, 90, 115),
            }

        if dark:
            cols = darkcols
        else:
            cols = lightcols
        return cols.get(method.lower(), default_col)

    def sc_color(self, table, sc, dark=False):
        default_col = table.getBackground()
        if len(sc) == 0:
            return default_col
        lightcols = {
            '2': Color(240, 255, 240),
            '3': Color(255, 240, 255),
            '4': Color(255, 240, 240),
            '5': Color(255, 255, 230),
        }

        darkcols = {
            '2': Color(90, 115, 90),
            '3': Color(115, 90, 115),
            '4': Color(115, 90, 90),
            '5': Color(115, 115, 80),
        }

        if dark:
            cols = darkcols
        else:
            cols = lightcols
        return cols.get(sc[0], default_col)

    def str_hash_code(self, s):
        h = 0
        n = len(s) - 1
        for c in s.encode():
            h += ord(c) * 31 ** n
        return h

    def str_color(self, s, lighten=0, seed=0):
        if s in RequestTableCellRenderer._str_colorcache:
            return RequestTableCellRenderer._str_colorcache[s]
        hashval = self.str_hash_code(str(s))+seed
        gen = random.Random()
        gen.seed(hashval)

        if lighten > 0:
            maxrand = 255-lighten
        else:
            maxrand = 255+lighten
        r = gen.randint(0, maxrand)
        g = gen.randint(0, maxrand)
        b = gen.randint(0, maxrand)

        if lighten > 0:
            r += lighten
            g += lighten
            b += lighten

        col = Color(r, g, b)
        RequestTableCellRenderer._str_colorcache[s] = col
        return col

    def _is_dark_mode(self, table):
        bg = table.getBackground()
        avgrgb = (bg.getRed() + bg.getGreen() + bg.getBlue())/3.0
        if avgrgb < 128:
            ret = True
        else:
            ret = False
        if RequestTableCellRenderer._was_dark_mode != ret:
            RequestTableCellRenderer._str_colorcache = {}
            RequestTableCellRenderer._was_dark_mode = ret
        return ret

    def get_cell_bg(self, table, value, rowIndex, columnIndex):
        darkmode = self._is_dark_mode(table)
        if columnIndex == 2:
            lg = 150
            if darkmode:
                lg = -lg
            return self.str_color(str(value), lighten=lg, seed=1)
        elif columnIndex == 3:
            return self.method_color(table, str(value), dark=darkmode)
        elif columnIndex == 5:
            return self.sc_color(table, str(value), dark=darkmode)
        return table.getBackground()

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, rowIndex, columnIndex):
        if (isSelected):
            self.setBackground(table.getSelectionBackground())
            self.setForeground(table.getSelectionForeground())
        else:
            self.setBackground(self.get_cell_bg(table, value, rowIndex, columnIndex))
            self.setForeground(table.getForeground())
        self.setText(str(value))
        return self

class RequestTable(JTable):
    def __init__(self, model, search_pane):
        JTable.__init__(self)

        self._search_pane = search_pane
        
        self.setModel(model)
        self.setAutoResizeMode(JTable.AUTO_RESIZE_OFF)
        self._table_sorter = TableRowSorter(model)
        self.setRowSorter(self._table_sorter)
        self.setDefaultRenderer(String("").getClass(), RequestTableCellRenderer())
        self.setDefaultRenderer(Integer(0).getClass(), RequestTableCellRenderer())

        self._history_model = model
        for i in range(model.getColumnCount()):
            col = self.getColumnModel().getColumn(i)
            col.setMinWidth(20)
            col.setPreferredWidth(model.getPreferredWidth(i))

    def changeSelection(self, row, col, toggle, extend):
        JTable.changeSelection(self, row, col, toggle, extend)
        ind = self.convertRowIndexToModel(row)
        entry = self._history_model._entries[ind]
        reqrsp = entry.get_request_response()
        self._search_pane.set_displayed_message(reqrsp)

class BirchSearchEntry(JPanel):
    class _HelpButtonHandler(ActionListener):
        def to_html(self, s):
            return "<html><body style='width: 600px'>" + s.replace("\n", "<br>") + "</body></html>"

        def actionPerformed(self, e):
            contents = JLabel(self.to_html(FILTER_HELP))
            scroll = JScrollPane(contents)
            dialog = JDialog()
            dialog.setBounds(100, 100, 600, 600)
            dialog.getContentPane().setLayout(BorderLayout(0, 0))
            dialog.getContentPane().add(scroll, BorderLayout.CENTER)
            dialog.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
            dialog.setVisible(True)
            
    def __init__(self, extender, search_pane):
        JPanel.__init__(self)
        self._extender = extender
        self._search_pane = search_pane
        self._active_filters = []

        self._active_filters_pane = JPanel()
        self._active_filters_pane.setLayout(BoxLayout(self._active_filters_pane, BoxLayout.PAGE_AXIS))

        self.setLayout(BorderLayout())

        title_pane = JPanel(BorderLayout())
        help_but = JButton("?")
        help_but.addActionListener(BirchSearchEntry._HelpButtonHandler())
        title_pane.add(help_but, BorderLayout.LINE_START)
        title_pane.add(JLabel("  Search Filters"), BorderLayout.CENTER)

        self.add(title_pane, BorderLayout.PAGE_START)
        self.add(SearchFilterEntry(self._extender, self), BorderLayout.PAGE_END)
        self.add(JScrollPane(self._active_filters_pane), BorderLayout.CENTER)

    def add_filter(self, f, _suppress_events=False):
        entry = ActiveFilterDisplay(self, f)
        d = entry.getMaximumSize()
        d.setSize(d.getWidth(), entry.getPreferredSize().getHeight())
        entry.setMaximumSize(d)
        self._active_filters_pane.add(entry)
        self._active_filters.append(entry)

        if not _suppress_events:
            self._filters_changed()

    def remove_filter(self, s):
        self._active_filters.remove(s)
        self._recreate_filter_pane()

    def serialize_filters(self):
        ret = []
        for f in self._active_filters:
            ret.append(f.filt.to_serialized())
        return ret

    def deserialize_filters(self, serialized):
        self._active_filters = []
        for srz in serialized:
            try:
                filt = StringSearchFilter.from_serialized(srz)
            except Exception as e:
                print(e)
            self.add_filter(filt, _suppress_events=True)
        self._recreate_filter_pane()

    def _filters_changed(self):
        self._active_filters_pane.revalidate()
        self._active_filters_pane.repaint()
        self._search_pane.filters_changed.invoke()

    def _recreate_filter_pane(self):
        self._active_filters_pane.removeAll()
        for p in self._active_filters:
            self._active_filters_pane.add(p)
        self._filters_changed()

    def check_model_entry(self, entry):
        for f in self._active_filters:
            if not f.filt.check_model_entry(entry):
                return False
        return True

class SearchFilter(object):
    def check_model_entry(self, entry):
        return True

    def get_label(self):
        return "<unknown filter>"

class InvalidFilter(Exception):
    def __init__(self, msg=""):
        if msg == "":
            msg = "Invalid filter"
        Exception.__init__(self, msg)

class SearchFilterEntry(JPanel, ActionListener):
    def __init__(self, extender, search_entry):
        JPanel.__init__(self)
        self._search_entry = search_entry
        self._extender = extender

        self.setLayout(BorderLayout())
        but = JButton("+")
        but.addActionListener(self)
        self.add(but, BorderLayout.LINE_START)

        self._filter_entry = JTextField()
        self._filter_entry.addActionListener(self)
        self.add(self._filter_entry, BorderLayout.CENTER)

    def actionPerformed(self, e):
        if self._filter_entry.getText() == "":
            return
        try:
            f = StringSearchFilter(self._filter_entry.getText())
            self._search_entry.add_filter(f)
            self._filter_entry.setText("")
        except (InvalidFilter, ValueError) as e:
            JOptionPane.showMessageDialog(JFrame(), str(e))

class ActiveFilterDisplay(JPanel, ActionListener):
    def __init__(self, search_entry, filt):
        JPanel.__init__(self)
        self._search_entry = search_entry
        self.filt = filt

        self.setBorder(BorderFactory.createEmptyBorder(1, 5, 1, 5))
        self.setLayout(BorderLayout())
        but = JButton("X")
        but.addActionListener(self)
        self.add(but, BorderLayout.LINE_START)
        lbl = JLabel(filt.get_label())
        lbl.setBorder(BorderFactory.createEmptyBorder(0, 5, 0, 0))
        self.add(lbl, BorderLayout.CENTER)

    def actionPerformed(self, e):
        self._search_entry.remove_filter(self)

##################
# Search filters #
##################

class StringSearchFilter(SearchFilter):
    def __init__(self, filter_string="", filter_args=None, *args, **kwargs):
        # init vars
        SearchFilter.__init__(self, *args, **kwargs)
        self.filter_string = filter_string
        self.filter_args = filter_args or shlex.split(filter_string)

        # init fields/checks
        self.invert_terms = ["invert", "inv"]
        
        self.single_fields = {
            "host": self.field_host,
            "path": self.field_path,
            "request_body": self.field_request_body,
            "response_body": self.field_response_body,
            "body": self.field_all_body,
            "all": self.field_all,
            "method": self.field_method,
            "url": self.field_url,
            "statuscode": self.field_statuscode,
            "tool": self.field_tool,
        }

        self.kv_fields = {
            "request_header": self.kv_field_request_headers,
            "postparam": self.kv_field_post_params,
            "urlparam": self.kv_field_post_params,
            "param": self.kv_field_all_params,
            "reqcookie": self.kv_field_request_cookies,
            "rspcookie": self.kv_field_response_cookies,
            "cookie": self.kv_field_all_cookies,
        }

        self.unary_checks = {
            "exists": self.check_exists,
        }

        self.binary_checks = {
            "is": self.check_is,
            "iscs": self.check_iscs,
            "contains": self.check_contains,
            "containscs": self.check_containscs,
            "containsr": self.check_containsr,
            "leneq": self.check_leneq,
            "lengt": self.check_lengt,
            "lenlt": self.check_lenlt,
        }

        # aliases
        self.single_field_aliases = {
            "reqbd": "request_body",
            "qbd": "request_body",
            "qdata": "request_body",
            "qdt": "request_body",

            "rspbd": "response_body",
            "sbd": "response_body",
            "sdata": "response_body",
            "sdt": "response_body",

            "bd": "body",
            "data": "body",
            "dt": "body",

            "verb": "method",
            "vb": "method",

            "domain": "host",
            "hs": "host",
            "dm": "host",

            "pt": "path",

            "sc": "statuscode",
        }

        self.kv_field_aliases = {
            "qhd": "request_header",
            "reqhd": "request_header",

            "shd": "response_header",
            "rsphd": "response_header",

            "hd": "header",

            "uparam": "urlparam",

            "pparam": "postparam",

            "pm": "param",

            "rspck": "rspcookie",
            "sck": "rspcookie",

            "reqck": "reqcookie",
            "qck": "reqcookie",

            "ck": "cookie",
        }

        self.unary_check_aliases = {
            "ex": "exists",
        }

        self.binary_check_aliases = {
            "ct": "contains",

            "ctcs": "containscs",

            "ctr": "containsr",
        }

        # validate minimum
        if len(self.filter_args) == 0:
            raise InvalidFilter("No field provided to filter by")

        if len(self.filter_args) == 1:
            raise InvalidFilter("No check provided to be performed on the message")

        if self.filter_args[0] in self.invert_terms:
            invert = True
            self.filter_args = self.filter_args[1:]
        else:
            invert = False

        field_type = self.get_field_type(self.filter_args[0])
        if field_type == "single":
            if len(self.filter_args) == 3:
                self._check_func = self.get_binary_request_check_function(self.filter_args[0], self.filter_args[1], self.filter_args[2], invert=invert)
                return

            if len(self.filter_args) == 2:
                self._check_func = self.get_unary_request_check_function(self.filter_args[0], self.filter_args[1], invert=invert)
                return

            raise InvalidFilter("Invalid number of arguments")
        elif field_type == "kv":
            self._check_func = self.get_kv_request_check_function(self.filter_args[0], self.filter_args[1:], invert=invert)
            return

        raise InvalidFilter("Invalid filter")

    def to_serialized(self):
        return {'s': self.filter_string, 'a': self.filter_args}

    @classmethod
    def from_serialized(cls, j):
        filter_string = j['s']
        filter_args = j['a']
        return cls(filter_string=filter_string, filter_args=filter_args)

    # getting functions from keys
    def get_field_type(self, key):
        if key in self.invert_terms:
            return "invert"
        if self.get_field_function(key) is not None:
            return "single"
        if self.get_kv_field_function(key) is not None:
            return "kv"
        return ""

    def get_operator_type(self, key):
        if self.get_binary_check_function(key) is not None:
            return "binary"
        if self.get_unary_check_function(key) is not None:
            return "unary"
        return ""

    def get_field_function(self, key):
        if key in self.single_field_aliases:
            key = self.single_field_aliases[key]
        return self.single_fields.get(key, None)

    def get_kv_field_function(self, key):
        if key in self.kv_field_aliases:
            key = self.kv_field_aliases[key]
        return self.kv_fields.get(key, None)

    def get_binary_check_function(self, key):
        if key in self.binary_check_aliases:
            key = self.binary_check_aliases[key]
        return self.binary_checks.get(key, None)

    def get_unary_check_function(self, key):
        if key in self.unary_check_aliases:
            key = self.unary_check_aliases[key]
        return self.unary_checks.get(key, None)

    # returns a function that takes in a list of pairs and returns true/false
    def get_kv_check_functions(self, args):
        if len(args) == 0:
            raise InvalidFilter("Invalid number of arguments")

        # pop op1
        op1 = args[0]
        args = args[1:]

        # get op1 function
        op1_type = self.get_operator_type(op1)
        if op1_type == 'unary':
            f1 = self.get_unary_check_function(op1)
        elif op1_type == 'binary':
            if len(args) == 0:
                raise InvalidFilter("Invalid number of arguments")
            # pop op1's value
            op1_val = args[0]
            args = args[1:]

            # f1 takes in a value and compares it to op1's value
            f = self.get_binary_check_function(op1)
            f1 = lambda s: f(s, op1_val)
        else:
            raise InvalidFilter()

        f2 = None
        if len(args) > 0:
            # get op2 function
            op2 = args[0]
            args = args[1:]
            op2_type = self.get_operator_type(op2)
            if op2_type == 'unary':
                f2 = self.get_unary_check_function(op2)
            elif op2_type == 'binary':
                if len(args) == 0:
                    raise InvalidFilter("Invalid number of arguments")
                # pop op2's value
                op2_val = args[0]
                args = args[1:]

                # f2 takes in a value and compares it to op2's value
                f = self.get_binary_check_function(op2)
                f2 = lambda s: f(s, op2_val)
            else:
                raise InvalidFilter()

        return f1, f2

    # getting request checker functions
    def get_binary_request_check_function(self, field_key, check_key, value, invert=False):
        field_func = self.get_field_function(field_key)
        if field_func is None:
            raise InvalidFilter("Invalid field: %s" % field_key)
        check_func = self.get_binary_check_function(check_key)
        if check_func is None:
            raise InvalidFilter("Invalid comparer: %s" % check_key)
        return lambda entry: check_func(field_func(entry), value) != invert

    def get_unary_request_check_function(self, field_key, check_key, invert=False):
        field_func = self.get_field_function(field_key)
        if field_func is None:
            raise InvalidFilter("Invalid field: %s" % field_key)
        check_func = self.get_unary_check_function(check_key)
        if check_func is None:
            raise InvalidFilter("Invalid comparer: %s" % check_key)
        return lambda entry: check_func(field_func(entry)) != invert

    def get_kv_request_check_function(self, field_key, args, invert=False):
        field_func = self.get_kv_field_function(field_key)
        if field_func is None:
            raise InvalidFilter("Invalid field: %s" % field_key)
        f1, f2 = self.get_kv_check_functions(args)
        if f1 is None:
            raise InvalidFilter("Invalid comparer: %s" % args[0])
        return lambda entry: self.check_kv(field_func(entry), f1, f2) != invert

    def check_kv(self, pairs, f1, f2):
        for k, v in pairs:
            if f2 is None:
                # if we only have 1 function, succeed if either match our function
                if f1(k) or f1(v):
                    return True
            else:
                # if we have 2 functions, succeed if the first function matches the key and the second function matches the value
                if f1(k) and f2(v):
                    return True
        return False

    # Single Fields
    def field_host(self, entry):
        return entry.get_request_response().getHttpService().getHost()

    def field_path(self, entry):
        return entry.request_info.getUrl().getPath()

    def field_request_body(self, entry):
        reqrsp = entry.get_request_response()
        req = reqrsp.getRequest()
        return req[entry.request_info.getBodyOffset():].tostring()

    def field_response_body(self, entry):
        rsp = entry.get_request_response().getResponse()
        if rsp is None:
            return ""
        if entry.response_info is None:
            return ""
        return rsp[entry.response_info.getBodyOffset():].tostring()

    def field_all_body(self, entry):
        return self.field_request_body(entry) + self.field_response_body(entry)

    def field_all(self, entry):
        reqrsp = entry.get_request_response()
        ret = reqrsp.getRequest().tostring()
        rsp = reqrsp.getResponse()
        if rsp is not None:
            ret = ret + "\r\n" + rsp.tostring()
        return ret

    def field_method(self, entry):
        return entry.request_info.getMethod()

    def field_url(self, entry):
        return entry.request_info.getUrl().toString()

    def field_statuscode(self, entry):
        if entry.response_info is None:
            return ""
        return str(entry.response_info.getStatusCode())

    def field_tool(self, entry):
        return entry.tool

    # Key/Value Fields
    def kv_field_request_headers(self, entry):
        headers_list = entry.request_info.getHeaders().toArray().tolist()
        ret = []
        for hstr in headers_list:
            parts = hstr.split(": ", 1)
            p0 = parts[0]
            if len(parts) > 1:
                p1 = parts[1]
            else:
                p1 = ""
            ret.append((p0, p1))
        return ret

    def kv_field_response_headers(self, entry):
        if entry.response_info is None:
            return []
        headers_list = entry.response_info.getHeaders().toArray().tolist()
        ret = []
        for hstr in headers_list:
            parts = hstr.split(": ", 1)
            p0 = parts[0]
            if len(parts) > 1:
                p1 = parts[1]
            else:
                p1 = ""
            ret.append((p0, p1))
        return ret

    def kv_field_all_headers(self, entry):
        return self.kv_field_request_headers(entry) + self.kv_field_response_headers(entry)

    def _get_params(self, entry, ptypes=None):
        param_list = entry.request_info.getParameters()
        ret = []
        for p in param_list:
            if ptypes is not None and p.getType() not in ptypes:
                continue
            ret.append((p.getName(), p.getValue()))
        return ret

    def kv_field_post_params(self, entry):
        return self._get_params(entry, [burp.IParameter.PARAM_BODY])

    def kv_field_url_params(self, entry):
        return self._get_params(entry, [burp.IParameter.PARAM_URL])

    def kv_field_all_params(self, entry):
        return self._get_params(entry, [
            burp.IParameter.PARAM_BODY,
            burp.IParameter.PARAM_JSON,
            burp.IParameter.PARAM_MULTIPART_ATTR,
            burp.IParameter.PARAM_URL,
            burp.IParameter.PARAM_XML,
            burp.IParameter.PARAM_XML_ATTR,
        ])

    def kv_field_request_cookies(self, entry):
        return self._get_params(entry, [burp.IParameter.PARAM_COOKIE])

    def kv_field_response_cookies(self, entry):
        if entry.response_info is None:
            return []
        ret = []
        for c in entry.response_info.getCookies():
            ret.append((c.getName(), c.getValue()))
        return ret

    def kv_field_all_cookies(self, entry):
        return self.kv_field_request_cookies(entry) + self.kv_field_response_cookies(entry)

    # Unary checks
    def check_exists(self, v):
        if v is None:
            return False
        if v == "":
            return False
        return True

    # Normal checks
    def check_is(self, s, v):
        s = s.encode("ascii", "ignore")
        return v.lower() == s.lower()

    def check_iscs(self, s, v):
        s = s.encode("ascii", "ignore")
        return v == s

    def check_contains(self, s, v):
        s = s.encode("ascii", "ignore")
        return v.lower() in s.lower()

    def check_containscs(self, s, v):
        s = s.encode("ascii", "ignore")
        return v in s

    def check_containsr(self, s, v):
        s = s.encode("ascii", "ignore")
        match = re.search(v, s)
        return match != None

    def check_leneq(self, s, v):
        try:
            n = int(v)
        except ValueError:
            return False
        return len(s) == n

    def check_lengt(self, s, v):
        try:
            n = int(v)
        except ValueError:
            return False
        return len(s) > n

    def check_lenlt(self, s, v):
        try:
            n = int(v)
        except ValueError:
            return False
        return len(s) < n

    # implement filter
    def get_label(self):
        return self.filter_string

    def check_model_entry(self, model_entry):
        return self._check_func(model_entry)

def ps2jb(arr):
    """
    Turns Python str into Java byte arrays
    :param arr: 'AAA'
    :return: [65, 65, 65]
    """
    return [ord(x) if ord(x) < 128 else ord(x) - 256 for x in arr]

def jb2ps(arr):
    """
    Turns Java byte arrays into Python str
    :param arr: [65, 65, 65]
    :return: 'AAA'
    """
    return ''.join(map(lambda x: chr(x % 256), arr))

def u2s(uni):
    """
    Turns unicode into str/bytes. Burp might pass invalid Unicode (e.g. Intruder Bit Flipper).
    This seems to be the only way to say "give me the raw bytes"
    :param uni: u'https://example.org/invalid_unicode/\xc1'
    :return: 'https://example.org/invalid_unicode/\xc1'
    """
    if isinstance(uni, unicode):
        return uni.encode("iso-8859-1", "ignore")
    else:
        return uni
