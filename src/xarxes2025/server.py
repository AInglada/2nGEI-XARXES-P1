import socket
import threading
from loguru import logger
# from xarxes2025.udpdatagram import UDPDatagram
# from xarxes2025.videoprocessor import VideoProcessor


class Server(object):
    def __init__(self, port):       
        """
        Initialize a new VideoStreaming server.

        :param port: The port to listen on.
        """
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
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
            client_thread.start()

    def handle_client(self, client_socket):
        """Manage communication with a client"""
        state = "INIT"  # Initialize state here
        while True:
            try:
                request = client_socket.recv(1024).decode().strip()
                if not request:
                    break

                logger.info(f"Recived from client:\n{request}")

                # Get order type (SETUP, PLAY, PAUSE, TEARDOWN)
                request_lines = request.split("\n")
                command = request_lines[0].split()[0]  # First word of the first line

                if command == "SETUP" and state == "INIT":
                    state = "READY"
                    response = "RTSP/1.0 200 OK\nCSeq: 1\nSession: 1234567890\n\n"

                elif command == "PLAY" and state == "READY":
                    state = "PLAYING"
                    response = "RTSP/1.0 200 OK\nCSeq: 2\nSession: 1234567890\n\n"

                elif command == "PAUSE" and state == "PLAYING":
                    state = "READY"
                    response = "RTSP/1.0 200 OK\nCSeq: 3\nSession: 1234567890\n\n"

                elif command == "TEARDOWN":
                    state = "INIT"
                    response = "RTSP/1.0 200 OK\nCSeq: 4\nSession: 1234567890\n\n"
                    client_socket.send(response.encode())
                    break  # End connection

                else:
                    response = "RTSP/1.0 400 Bad Request\n\n"

                client_socket.send(response.encode())

            except Exception as e:
                logger.info(f"Error with client: {e}")
                break

        client_socket.close()
        logger.info("Offline client")

    # # 
    # # This is not complete code, it's just an skeleton to help you get started.
    # # You will need to use these snippets to do the code.
    # # 
    # #     
    # def send_udp_frame(self):
      
    #     # This snippet reads from self.video (a VideoProcessor object) and prepares 
    #     # the frame to be sent over UDP. 

    #     data = self.video.next_frame()
    #     if data:
    #         if len(data)>0:
    #                 frame_number = self.get_frame_number()
    #                 # create UDP Datagram

    #                 udp_datagram = UDPDatagram(frame_number, data).get_datagram()

    #                 # send UDP Datagram
    #                 socketudp.sendto(udp_datagram, (address, port))
                        
