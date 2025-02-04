# This file is part of Jeedom.
#
# Jeedom is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Jeedom is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
#

import time
import logging
import threading
import requests
import datetime
import collections
import serial
import os
from os.path import join
import socket
from Queue import Queue
import SocketServer
from SocketServer import (TCPServer, StreamRequestHandler)
import signal
import unicodedata
import pyudev

# ------------------------------------------------------------------------------

class jeedom_com():
	def __init__(self,apikey = '',url = '',cycle = 0.5):
		self.apikey = apikey
		self.url = url
		self.cycle = cycle
		self.changes = {}
		self.send_changes_async()
		logging.debug('Init request module v%s' % (str(requests.__version__),))

	def send_changes_async(self):
		try:
			if len(self.changes) == 0:
				resend_changes = threading.Timer(self.cycle, self.send_changes_async)
				resend_changes.start() 
				return
			start_time = datetime.datetime.now()
			changes = self.changes
			self.changes = {}
			try:
				logging.debug('Send to jeedom :  %s' % (str(changes),))
				r = requests.post(self.url + '?apikey=' + self.apikey, json=changes, timeout=(0.5, 120), verify=False)
				if r.status_code != requests.codes.ok:
					logging.error('Error on send request to jeedom, return code %s' % (str(r.status_code),))
			except Exception as error:
				logging.error('Error on send request to jeedom %s' % (str(error),))
			dt = datetime.datetime.now() - start_time
			ms = (dt.days * 24 * 60 * 60 + dt.seconds) * 1000 + dt.microseconds / 1000.0
			timer_duration = self.cycle - ms
			if timer_duration < 0.1:
				timer_duration = 0.1
			resend_changes = threading.Timer(timer_duration, self.send_changes_async)
			resend_changes.start() 
		except Exception as error:
			logging.error('Critical error on  send_changes_async %s' % (str(error),))
			resend_changes = threading.Timer(self.cycle, self.send_changes_async)
			resend_changes.start() 
		
	def add_changes(self, key, value):
		if key.find('::') != -1:
			tmp_changes = {}
			changes = value
			for k in reversed(key.split('::')):
				if k not in tmp_changes:
					tmp_changes[k] = {}
				tmp_changes[k] = changes
				changes = tmp_changes
				tmp_changes = {}
			self.merge_dict(self.changes,changes)
		else:
			self.changes[key] = value

	def send_change_immediate(self, change):
		try:
			logging.debug('Send to jeedom :  %s' % (str(change),))
			r = requests.post(self.url + '?apikey=' + self.apikey, json=change, timeout=(0.5, 120), verify=False)
			if r.status_code != requests.codes.ok:
				logging.error('Error on send request to jeedom, return code %s' % (str(r.status_code),))
		except Exception as error:
			logging.error('Error on send request to jeedom %s' % (str(error),))

	def set_change(self,changes):
		self.changes = changes

	def get_change(self):
		return self.changes

	def merge_dict(self, d1, d2):
		for k, v2 in d2.items():
			v1 = d1.get(k)  # returns None if v1 has no value for this key
			if (isinstance(v1, collections.Mapping) and
					isinstance(v2, collections.Mapping)):
				self.merge_dict(v1, v2)
			else:
				d1[k] = v2

	def test(self):
		try:
			response = requests.get(self.url + '?apikey=' + self.apikey, verify=False)
			if response.status_code != requests.codes.ok:
				logging.error('Callback error: %s %s. Please check your network configuration page'% (response.status_code, response.reason,))
				logging.error(response.text)
				return False
		except Exception as e:
			logging.error('Callback result as a unknown error: %s. Please check your network configuration page'% (e.message,))
			return False
		return True

# ------------------------------------------------------------------------------

class jeedom_utils():

	@staticmethod
	def convert_log_level(level = 'error'):
		LEVELS = {'debug': logging.DEBUG,
          'info': logging.INFO,
          'notice': logging.WARNING,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL,
          'none': logging.NOTSET}
		return LEVELS.get(level, logging.NOTSET)

	@staticmethod
	def set_log_level(level = 'error'):
		FORMAT = '[%(asctime)-15s][%(levelname)s] : %(message)s'
		logging.basicConfig(level=jeedom_utils.convert_log_level(level),format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

	@staticmethod
	def find_tty_usb(idVendor, idProduct, product = None):
		context = pyudev.Context()
		for device in context.list_devices(subsystem='tty'):
			if 'ID_VENDOR' not in device:
				continue
			if device['ID_VENDOR_ID'] != idVendor:
				continue
			if device['ID_MODEL_ID'] != idProduct:
				continue
			if product is not None:
				if 'ID_VENDOR' not in device or device['ID_VENDOR'].lower().find(product.lower()) == -1 :
					continue
			return str(device.device_node)
		return None

	@staticmethod
	def stripped(str):
		return "".join([i for i in str if ord(i) in range(32, 127)])

	@staticmethod
	def ByteToHex( byteStr ):
		return ''.join( [ "%02X " % ord( x ) for x in str(byteStr) ] ).strip()

	@staticmethod
	def dec2bin(x, width=8):
		return ''.join(str((x>>i)&1) for i in xrange(width-1,-1,-1))

	@staticmethod
	def dec2hex(dec):
		if dec is None:
			return 0
		return hex(dec)[2:]

	@staticmethod
	def testBit(int_type, offset):
		mask = 1 << offset
		return(int_type & mask)

	@staticmethod
	def clearBit(int_type, offset):
		mask = ~(1 << offset)
		return(int_type & mask)

	@staticmethod
	def split_len(seq, length):
		return [seq[i:i+length] for i in range(0, len(seq), length)]

	@staticmethod
	def write_pid(path):
		pid = str(os.getpid())
		logging.debug("Writing PID " + pid + " to " + str(path))
		file(path, 'w').write("%s\n" % pid)
		
	@staticmethod
	def remove_accents(input_str):
		nkfd_form = unicodedata.normalize('NFKD', unicode(input_str))
		return u"".join([c for c in nkfd_form if not unicodedata.combining(c)])

# ------------------------------------------------------------------------------

class jeedom_serial():

	def __init__(self,device = '',rate = '',timeout = 9):
		self.device = device
		self.rate = rate
		self.timeout = timeout
		self.port = None
		logging.debug('Init serial module v%s' % (str(serial.VERSION),))

	def open(self):
		if self.device:
			logging.debug("Open serial port on device: " + str(self.device)+', rate '+str(self.rate)+', timeout : '+str(self.timeout))
		else:
			logging.error("Device name missing.")
			return False
		logging.debug("Open Serialport")
		try:  
			self.port = serial.Serial(self.device,self.rate,timeout=self.timeout)
		except serial.SerialException, e:
			logging.error("Error: Failed to connect on device " + self.device + " Details : " + str(e))
			return False
		if not self.port.isOpen():
			self.port.open()
		self.flushOutput()
		self.flushInput()
		return True

	def close(self):
		logging.debug("Close serial port")
		try:
			self.port.close()
			logging.debug("Serial port closed")
			return True
		except:
			logging.error("Failed to close the serial port (" + self.device + ")")
			return False

	def write(self,data):
		logging.debug("Write data to serial port : "+str(jeedom_utils.ByteToHex(data)))
		self.port.write(data)

	def flushOutput(self,):
		logging.debug("flushOutput serial port ")
		self.port.flushOutput()

	def flushInput(self):
		logging.debug("flushInput serial port ")
		self.port.flushInput()

	def read(self):
		try:
			if self.port.inWaiting() != 0:
				return self.port.read()
		except IOError, e:
			logging.error("Serial read error: %s" % (str(e)))
		return None

	def readbytes(self,number):
		buf = ''
		for i in range(number):
			try:
				byte = self.port.read()
			except IOError, e:
				logging.error("Error: %s" % e)
			except OSError, e:
				logging.error("Error: %s" % e)
			buf += byte
		return buf

# ------------------------------------------------------------------------------

JEEDOM_SOCKET_MESSAGE = Queue()

class jeedom_socket_handler(StreamRequestHandler):
	def handle(self):
		global JEEDOM_SOCKET_MESSAGE
		logging.debug("Client connected to [%s:%d]" % self.client_address)
		lg = self.rfile.readline()
		JEEDOM_SOCKET_MESSAGE.put(lg)
		logging.debug("Message read from socket: " + lg.strip())
		self.netAdapterClientConnected = False
		logging.debug("Client disconnected from [%s:%d]" % self.client_address)

class jeedom_socket():

	def __init__(self,address='localhost', port=55000):
		self.address = address
		self.port = port
		SocketServer.TCPServer.allow_reuse_address = True

	def open(self):
		self.netAdapter = TCPServer((self.address, self.port), jeedom_socket_handler)
		if self.netAdapter:
			logging.debug("Socket interface started")
			threading.Thread(target=self.loopNetServer, args=()).start()
		else:
			logging.debug("Cannot start socket interface")

	def loopNetServer(self):
		logging.debug("LoopNetServer Thread started")
		logging.debug("Listening on: [%s:%d]" % (self.address, self.port))
		self.netAdapter.serve_forever()
		logging.debug("LoopNetServer Thread stopped")

	def close(self):
		self.netAdapter.shutdown()

	def getMessage(self):
		return self.message

# ------------------------------------------------------------------------------
# END
# ------------------------------------------------------------------------------
