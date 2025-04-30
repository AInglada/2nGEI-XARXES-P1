import socket, threading, random, time, os
from loguru import logger
from xarxes2025.udpdatagram import UDPDatagram
from xarxes2025.videoprocessor import VideoProcessor

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
        session_id = None
        cseq = 0
        client_rtp_port = None
        client_ip = client_address[0]
        video = None
        play_event = threading.Event()
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
                cseq = None
                request_lines = request.split("\n")
                for line in request_lines:
                    if line.startswith("CSeq:"):
                        try:
                            cseq = int(line.split(":")[1].strip())
                        except ValueError:
                            logger.error("Invalid CSeq")
                            response = "RTSP/1.0 400 Bad Request\r\n\r\n"
                            client_socket.send(response.encode())
                            continue
                if cseq is None:
                    logger.error("Empty CSeq")
                    response = "RTSP/1.0 400 Bad Request\r\n\r\n"
                    client_socket.send(response.encode())
                    continue
                command = request_lines[0].split()[0]

                if command == "SETUP" and state == "INIT":
                    media_name = os.path.basename(request_lines[0].split()[1])
                    if not os.path.exists(media_name):
                        response = f"RTSP/1.0 404 Not Found\r\nCSeq: {cseq}\r\n\r\n"
                        client_socket.send(response.encode())
                        continue

                    try:
                        video = VideoProcessor(media_name)
                    except Exception as e:
                        logger.error(f"Couldn't open video: {e}")
                        response = f"RTSP/1.0 500 Internal Server Error\r\nCSeq: {cseq}\r\n\r\n"
                        client_socket.send(response.encode())
                        continue

                    transport = next((l for l in request_lines if l.startswith("Transport:")), None)
                    if not transport:
                        response = f"RTSP/1.0 400 Bad Request\r\nCSeq: {cseq}\r\n\r\n"
                        client_socket.send(response.encode())
                        continue

                    client_rtp_port = None
                    for part in transport.split(";"):
                        if "client_port" in part:
                            try:
                                client_rtp_port = int(part.split("=")[1].strip())
                            except (ValueError, IndexError):
                                logger.error("Invalid client port")
                                response = f"RTSP/1.0 400 Bad Request\r\nCSeq: {cseq}\r\n\r\n"
                                client_socket.send(response.encode())
                                continue
                    if client_rtp_port is None:
                        logger.error("client_port not found")
                        response = f"RTSP/1.0 400 Bad Request\r\nCSeq: {cseq}\r\n\r\n"
                        client_socket.send(response.encode())
                        continue

                    session_id = f"{random.randint(0, 9999999999):010d}"
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
                    play_event.set()
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())

                    play_thread = threading.Thread(
                        target=self.send_udp_frame,
                        args=(video, client_ip, client_rtp_port, play_event),
                        daemon=True
                    )
                    play_thread.start()

                elif command == "PAUSE" and state == "PLAYING":
                    play_event.clear()
                    state = "READY"
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())

                elif command == "TEARDOWN":
                    play_event.clear()
                    if play_thread and play_thread.is_alive():
                        play_thread.join()
                    response = f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\nSession: {session_id}\r\n\r\n"
                    client_socket.send(response.encode())
                    break

                else:
                    response = f"RTSP/1.0 400 Bad Request\r\nCSeq: {cseq}\r\n\r\n"
                    client_socket.send(response.encode())

            except Exception as e:
                logger.error(f"Error handling client: {e}")
                break

        play_event.clear()
        if play_thread:
            play_thread.join()
        client_socket.close()
        logger.info("Offline client")

    def send_udp_frame(self, video, client_ip, client_rtp_port, play_event):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            while play_event.is_set():
                data = video.next_frame()
                if not data:
                    logger.info(f"End of video stream")
                    break
                udp_packet = UDPDatagram(video.get_frame_number(), data).get_datagram()
                sock.sendto(udp_packet, (client_ip, client_rtp_port))
                time.sleep(0.025)
        except Exception as e:
            logger.error(f"UDP Error: {e}")
        finally:
            sock.close()