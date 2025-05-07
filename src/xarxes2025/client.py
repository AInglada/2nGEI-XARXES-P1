import sys
import socket
import threading
import io

from tkinter import Tk, Label, Button, W, E, N, S, messagebox
from loguru import logger
from PIL import Image, ImageTk
from xarxes2025.udpdatagram import UDPDatagram

class Client(object):
    def __init__(self, server_port, filename):
        logger.debug(f"Client created ")
        # RTSP variables
        self.server_ip = '127.0.0.1'
        self.server_port = server_port
        self.video_file = filename
        self.rtp_port = None
        self.rtsp_seq = 0
        self.session_id = None
        self.state = 'INIT'
        # Networking
        self.rtsp_socket = None
        self.rtp_socket = None
        self.rtp_thread = None
        self.is_receiving = False
        # UI
        self.root = None
        self.movie = None
        self.text = None
        self.create_ui()
        try:
            self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rtsp_socket.settimeout(5)  # 5 timeout sec
            self.rtsp_socket.connect((self.server_ip, self.server_port))
        except socket.timeout:
            messagebox.showerror("Error", "Timeout connecting to server")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Connection error: {str(e)}")
            return

    def create_ui(self):
        """
        Create the user interface for the client.

        This function creates the window for the client and its
        buttons and labels. It also sets up the window to call the
        close window function when the window is closed.

        :returns: The root of the window.
        """
        self.root = Tk()

        # Set the window title
        self.root.wm_title("RTP Client")

        # On closing window go to close window function
        self.root.protocol("WM_DELETE_WINDOW", self.ui_close_window)

        # Create Buttons
        self.setup = self._create_button("Setup", self.ui_setup_event, 0, 0)
        self.start = self._create_button("Play", self.ui_play_event, 0, 1)
        self.pause = self._create_button("Pause", self.ui_pause_event, 0, 2)
        self.teardown = self._create_button("Teardown", self.ui_teardown_event, 0, 3)

        # Create a label to display the movie
        self.movie = Label(self.root, height=29)
        self.movie.grid(row=1, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

        # Create a label to display text messages
        self.text = Label(self.root, height=3)
        self.text.grid(row=2, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

        return self.root

    def _create_button(self, text, command, row=0, column=0, width=20, padx=3, pady=3):
        """
        Create a button widget with the given text, command, and layout options.

        :param str text: The text to display on the button.
        :param callable command: The function to call when the button is clicked.
        :param int row: The row number of the button in the grid.
        :param int column: The column number of the button in the grid.
        :param int width: The width of the button.
        :param int padx: The horizontal padding of the button.
        :param int pady: The vertical padding of the button.
        :return: The button widget.
        """
        button = Button(self.root, width=width, padx=padx, pady=pady)
        button["text"] = text
        button["command"] = command
        button.grid(row=row, column=column, padx=2, pady=2)
        return button

    def ui_close_window(self):
        """
        Close the window.
        """
        self.is_receiving = False
        if self.rtp_thread and self.rtp_thread.is_alive():
            self.rtp_thread.join()
        if self.rtp_socket:
            self.rtp_socket.close()
        if self.rtsp_socket:
            self.rtsp_socket.close()
        self.root.destroy()
        logger.debug("Window closed")
        sys.exit(0)

    def ui_setup_event(self):
        """
        Handle the Setup button click event.
        """
        if self.state != 'INIT':
            messagebox.showerror("Error", "Can't SETUP now, please try to Teardown first")
            return
        logger.debug("Setup button clicked")
        self.text["text"] = "Setup button clicked"
        self.setup_movie()

    def ui_play_event(self):
        logger.debug("Play button clicked")
        self.text["text"] = "Sending PLAY..."
        if self.state != 'READY':
            messagebox.showerror("Error", "Not connected or prepared for PLAY")
            return
        try:
            self.play_movie()
            self.state = 'PLAYING'
        except Exception as e:
            messagebox.showerror("Error", f"Playing error: {str(e)}")
            self.state = 'READY'

    def ui_pause_event(self):
        logger.debug("Pause button clicked")
        self.text["text"] = "Sending PAUSE..."
        if self.state != 'PLAYING' or not self.rtsp_socket:
            messagebox.showerror("Error", "Not connected or prepared for PAUSE")
            return
        try:
            self.pause_movie()
            self.state = 'READY'
        except Exception as e:
            messagebox.showerror("Error", f"Pause error: {str(e)}")

    def ui_teardown_event(self):
        logger.debug("Teardown button clicked")
        self.text["text"] = "Sending TEARDOWN..."
        if self.state == 'INIT':
            messagebox.showerror("Error", f"Client not initialized")
            return

        try:
            self.teardown_movie()
            self.state = 'INIT'
        except Exception as e:
            messagebox.showerror("Error", f"Closing error: {str(e)}")

    def setup_movie(self):
        self.rtsp_seq += 1
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.settimeout(5)
        self.rtp_socket.bind(("", 0))  # Let OS assign free port
        self.rtp_port = self.rtp_socket.getsockname()[1]  # Get actual port
        logger.info(f"RTP socket bound to port {self.rtp_port}")

        req = f"SETUP {self.video_file} RTSP/1.0\r\n"
        req += f"CSeq: {self.rtsp_seq}\r\n"
        req += f"Transport: RTP/UDP; client_port={self.rtp_port}\r\n\r\n"
        self.rtsp_socket.send(req.encode())
        logger.debug(f"Sent RTSP SETUP:\n{req}")

        resp = self.rtsp_socket.recv(1024).decode()
        logger.debug(f"Received RTSP SETUP response:\n{resp}")
        for line in resp.split("\r\n"):
            if line.startswith("Session:"):
                self.session_id = line.split(":")[1].strip()
                logger.debug(f"Session ID: {self.session_id}")
        logger.debug("SETUP Complete")
        self.state = 'READY'
        self.text["text"] = "Setup complete"

    def play_movie(self):
        # RTSP PLAY
        self.rtsp_seq += 1
        req = f"PLAY {self.video_file} RTSP/1.0\r\n"
        req += f"CSeq: {self.rtsp_seq}\r\n"
        req += f"Session: {self.session_id}\r\n\r\n"
        self.rtsp_socket.send(req.encode())
        logger.debug(f"Sent RTSP PLAY:\n{req}")

        resp = self.rtsp_socket.recv(1024).decode()
        if "200 OK" not in resp:
            messagebox.showerror("Error", f"Server error: {resp.splitlines()[0]}")
            return
        logger.debug(f"Received RTSP PLAY response:\n{resp}")
        self.state = 'PLAYING'
        self.is_receiving = True
        self.text["text"] = "Playing"
        self.rtp_thread = threading.Thread(target=self.recv_rtp, daemon=True)
        self.rtp_thread.start()

    def pause_movie(self):
        # RTSP PAUSE
        self.rtsp_seq += 1
        req = f"PAUSE {self.video_file} RTSP/1.0\r\n"
        req += f"CSeq: {self.rtsp_seq}\r\n"
        req += f"Session: {self.session_id}\r\n\r\n"
        self.rtsp_socket.send(req.encode())
        logger.debug(f"Sent RTSP PAUSE:\n{req}")

        resp = self.rtsp_socket.recv(1024).decode()
        if "200 OK" not in resp:
            messagebox.showerror("Error", f"Server error: {resp.splitlines()[0]}")
            self.state = 'READY'
            return
        logger.debug(f"Received RTSP PAUSE response:\n{resp}")
        self.state = 'READY'
        self.is_receiving = False
        self.text["text"] = "Paused"

    def teardown_movie(self):
        # RTSP TEARDOWN
        self.rtsp_seq += 1
        req = f"TEARDOWN {self.video_file} RTSP/1.0\r\n"
        req += f"CSeq: {self.rtsp_seq}\r\n"
        req += f"Session: {self.session_id}\r\n\r\n"
        self.rtsp_socket.send(req.encode())
        logger.debug(f"Sent RTSP TEARDOWN:\n{req}")

        resp = self.rtsp_socket.recv(1024).decode()
        logger.debug(f"Received RTSP TEARDOWN response:\n{resp}")

        self.state = 'INIT'
        self.rtsp_seq = 0
        self.is_receiving = False
        self.session_id = None
        self.rtsp_seq = 0

        if self.rtp_socket:
            self.rtp_socket.close()
            self.rtp_socket = None

        self.text["text"] = "Teardown complete"

    def recv_rtp(self):
        while self.is_receiving:
            try:
                packet_bytes, _ = self.rtp_socket.recvfrom(65536)
                packet = UDPDatagram(0, b"")
                packet.decode(packet_bytes)
                payload = packet.get_payload()
                self.updateMovie(payload)
            except Exception:
                break
        logger.info("Stopped RTP reception")

    def updateMovie(self, data):
        """Update the video frame in the GUI from the byte buffer we received."""

        # data hauria de tenir el payload de la imatge extreta del paquet RTP
        # Com no en teniu, encara, us poso un exemple de com carregar una imatge
        # des del disc dur. Això ho haureu de canviar per carregar la imatge
        # des del buffer de bytes que rebem del servidor.
        # photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))

        try:
            photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
            self.movie.configure(image=photo, height=380)
            self.movie.photo_image = photo
        except Exception as e:
            logger.error(f"Failed to update frame: {e}")