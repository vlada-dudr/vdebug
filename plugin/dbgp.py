import socket
import xml.etree.ElementTree as ET

"""This module provides classes for speaking with debuggers that use the DBGP protocol.

These classes are language independent, and can be used without external modules.
"""

class Connection:
    """DBGP connection class, for managing the connection to the debugger.

    The host, port and socket timeout are configurable on object construction.
    """

    sock = None
    isconned = 0

    def __init__(self, host = '', port = 9000, timeout = 30):
        """Create a new Connection.

        The connection is not established until open() is called.

        host -- host name where debugger is running (default '')
        port -- port number which debugger is listening on (default 9000)
        timeout -- time in seconds to wait for a debugger connection before giving up (default 30)
        """
        self.port = 9000
        self.host = host
        self.timeout = timeout

    def __del__(self):
        """Make sure the connection is closed."""
        self.close()

    def isconnected(self):
        """Whether the connection has been established."""
        return self.isconned

    def open(self):
        """Listen for a connection from the debugger.

        The socket is blocking, and it will wait for the length of
        time given by the timeout (default is 30 seconds).
        """
        print 'Waiting for a connection (this message will self-destruct in ',self.timeout,' seconds...)'
        serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serv.settimeout(self.timeout)
            serv.bind((self.host, self.port))
            serv.listen(5)
            (self.sock, address) = serv.accept()
            self.sock.settimeout(None)
        except socket.timeout, e:
            serv.close()
            self.stop()
            raise e

        print 'Found connection from', address
        self.isconned = 1
        serv.close()

    def close(self):
        """Close the connection."""
        if self.sock != None:
            self.sock.close()
            self.sock = None
        self.isconned = 0

    def __recv_length(self):
        """Get the length of the proceeding message."""
        length = ''
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError, 'Socket Closed'
            if c == '\0':
                return int(length)
            if c.isdigit():
                length = length + c

    def __recv_null(self):
        """Receive a null byte."""
        while 1:
            c = self.sock.recv(1)
            if c == '':
                self.close()
                raise EOFError, 'Socket Closed'
            if c == '\0':
                return

    def __recv_body(self, to_recv):
        """Receive a message of a given length.

        to_recv -- length of the message to receive
        """
        body = ''
        while to_recv > 0:
            buf = self.sock.recv(to_recv)
            if buf == '':
                self.close()
                raise EOFError, 'Socket Closed'
            to_recv -= len(buf)
            body = body + buf
        return body

    def recv_msg(self):
        """Receive a message from the debugger.
        
        Returns a string, which is expected to be XML.
        """
        length = self.__recv_length()
        body     = self.__recv_body(length)
        self.__recv_null()
        return body

    def send_msg(self, cmd):
        """Send a message to the debugger.

        cmd -- command to send
        """
        self.sock.send(cmd + '\0')

class Protocol:
    """Interface for DBGP commands.

    Uses a Connection object to read and write with the debugger,
    and builds commands and returns the results.
    """

    conn = None
    transID = 0

    def __init__(self,connection):
        """Create a new Protocol using a Connection object.

        The Connection object specifies the debugger connection,
        and the Protocol provides a OO interface to interacting
        with it.

        connection -- The Connection object to use
        """
        self.language = None
        self.protocol = None
        self.idekey = None
        self.conn = connection
        if self.conn.isconnected() == 0:
            self.conn.open()
        self.__parse_init_msg(self.conn.recv_msg())
        
    def __parse_init_msg(self,msg):
        """Parse the init message from the debugger"""
        xml = ET.fromstring(msg)
        self.language = xml.get("language")
        if self.language == None:
            raise ResponseError(
                "Invalid XML response from debugger",
                msg)
        self.version = xml.get("protocol_version")
        self.idekey = xml.get("idekey")

    def send_cmd(self,cmd,args = '',res_cls = Response):
        """Send a command to the debugger.

        This method automatically adds a unique transaction
        ID to the command which is required by the debugger.

        Returns a Response object, which contains the
        response message and command.

        cmd -- the command name, e.g. 'status'
        args -- arguments for the command, which is optional 
                for certain commands (default '')
        """
        args = args.strip()
        send = cmd.strip()
        self.transID += 1
        send += ' -i '+ str(self.transID)
        if len(args) > 0:
            send += ' ' + args
        self.conn.send_msg(send)
        msg = self.conn.recv_msg()
        return res_cls(msg,cmd,args)

    def status(self):
        """Get the debugger status.
        
        Returns a Response object.
        """
        return self.send_cmd('status')

    def feature_get(self,name):
        """Get the value of a feature from the debugger.

        See the DBGP documentation for a list of features.
        
        Returns a FeatureGetResponse object.
        
        name -- name of the feature, e.g. encoding
        """
        return self.send_cmd(
                'feature_get',
                '-n '+str(name),
                FeatureGetResponse)

    def feature_set(self,name,value):
        """Set the value of a debugger feature.

        See the DBGP documentation for a list of features.
        
        Returns a Response object.
        
        name -- name of the feature, e.g. encoding
        value -- new value for the feature
        """
        return self.send_cmd(
                'feature_set',
                '-n ' + str(name) + ' -v ' + str(value))


""" Response objects """

class Response:
    """Contains response data from a command made to the debugger."""

    def __init__(self,response,cmd,cmd_args):
        self.response = response
        self.cmd = cmd
        self.cmd_args = cmd_args
        self.xml = None

    def get_cmd(self):
        """Get the command that created this response."""
        return self.cmd

    def get_cmd_args(self):
        """Get the arguments to the command."""
        return self.cmd_args

    def as_string(self):
        """Return the full response as a string.
        
        There is a __str__ method, which will render the
        whole object as a string and should be used for
        displaying.
        """
        return self.response

    def as_xml(self):
        """Get the response as element tree XML.

        Returns an xml.etree.ElementTree.Element object.
        """
        if self.xml == None:
            self.xml = ET.fromstring(self.response)
        return self.xml

    def __str__(self):
        return self.as_string()

class FeatureGetResponse(Response):
    """Response object specifically for the feature_get command."""

    def is_supported(self):
        """Whether the feature is supported or not."""
        xml = self.as_xml()
        return int(xml.get('supported'))

    def __str__(self):
        if self.is_supported():
            xml = self.as_xml()
            return xml.text
        else:
            return "* Feature not supported *"

""" Errors/Exceptions """

class DBGPError(Exception):
    """Raised when the debugger returns an error message."""
    pass

class ResponseError(Exception):
    """An error caused by an unexpected response from the
    debugger (e.g. invalid format XML)."""
    pass