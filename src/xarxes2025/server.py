import socket
import threading
from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor
import time


class Server(object):
    def __init__(self, port):
        """
        Initialize a new VideoStreaming server.

        :param port: The port to listen on.
        """
        self.video = None
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)  # Allow 5 concurent client
        logger.info(f"Server RTSP created listening port {self.port}")
        self.start()

    def start(self):
        """Listens for incoming connections and creates a thread for each client"""
        while True:
            client_socket, client_address = self.server_socket.accept()
            logger.info(f"Online client from {client_address}")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
            client_thread.start()

    def handle_client(self, client_socket, client_address):
        state = "INIT"
        session_id = "1234567890"
        cseq = 0
        client_rtp_port = None
        client_ip = client_address[0]
        video = None
        is_playing = False
        play_thread = None

        while True:
            try:
                data = ""
                while True:
                    chunk = client_socket.recv(1024).decode()
                    data += chunk
                    if "\n\n" in data or "\r\n\r\n" in data:
                        break
                request = data.strip()
                if not request:
                    break

                logger.info(f"Received from client:\n{request}")
                request_lines = request.split("\n")
                for line in request_lines:
                    if line.startswith("CSeq:"):
                        cseq = int(line.split(":")[1].strip())
                        break
                command = request_lines[0].split()[0]

                if command == "SETUP" and state == "INIT":
                    media_name = request_lines[0].split()[1]
                    transport = next((l for l in request_lines if l.startswith("Transport:")), None)
                    if transport:
                        for part in transport.split(";"):
                            if "client_port" in part:
                                client_rtp_port = int(part.split("=")[1])
                    try:
                        video = VideoProcessor(media_name)
                    except Exception as e:
                        logger.error(f"Could not open video file: {e}")
                        response = f"RTSP/1.0 500 Internal Server Error\r\nCSeq: {cseq}\r\n\r\n"
                        client_socket.send(response.encode())
                        continue

                    response = (
                        f"RTSP/1.0 200 OK\r\n"
                        f"CSeq: {cseq}\r\n"
                        f"Session: {session_id}\r\n"
                        f"Transport: RTP/UDP; client_port={client_rtp_port}\r\n\r\n"
                    )
                    state = "READY"
                    client_socket.send(response.encode())

                elif command == "PLAY" and state == "READY":
                    state = "PLAYING"
                    is_playing = True
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())

                    play_thread = threading.Thread(
                        target=self.send_udp_frame,
                        args=(video, client_ip, client_rtp_port, lambda: is_playing),
                        daemon=True
                    )
                    play_thread.start()

                elif command == "PAUSE" and state == "PLAYING":
                    is_playing = False
                    state = "READY"
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())

                elif command == "TEARDOWN":
                    is_playing = False
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())
                    break

                else:
                    response = f"RTSP/1.0 400 Bad Request\r\nCSeq: {cseq}\r\n\r\n"
                    client_socket.send(response.encode())

            except Exception as e:
                logger.error(f"Error handling client: {e}")
                break

        try:
            client_socket.close()
        except:
            pass
        logger.info("Offline client")

    def send_udp_frame(self, video, client_ip, client_rtp_port, playing_flag):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            while playing_flag():
                try:
                    data = video.next_frame()
                    if not data:
                        logger.info(f"End of video stream")
                        break
                    frame_number = video.get_frame_number()
                    udp_packet = UDPDatagram(frame_number, data).get_datagram()
                    sock.sendto(udp_packet, (client_ip, client_rtp_port))
                    time.sleep(0.05)
                except Exception as frame_err:
                    logger.error(f"Frame send error: {frame_err}")
                    break
        except Exception as e:
            logger.error(f"RTP socket error: {e}")
        finally:
            try:
                sock.close()
            except:
                pass