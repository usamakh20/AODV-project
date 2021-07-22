import logging
import threading
import traceback
from socket import *
from threading import Timer

# AODV Constants
AODV_HELLO_INTERVAL = 10
AODV_HELLO_TIMEOUT = 30
AODV_PATH_DISCOVERY_TIME = 30
AODV_ACTIVE_ROUTE_TIMEOUT = 300
AODV_HELLO_TYPE = "HELLO_MESSAGE"
USER_MESSAGE = "USER_MESSAGE"
AODV_RREQ_MESSAGE = "RREQ_MESSAGE"
AODV_RREP_MESSAGE = "RREP_MESSAGE"
AODV_RRER_MESSAGE = "RERR_MESSAGE"


class Aodv:
    # Constructor
    def __init__(self, name):
        self.node_name = name
        self.routes = []
        self.receiver_sock = socket(AF_INET, SOCK_DGRAM)  # Aodv receiver socket
        self.receiver_sock.bind(('localhost', 0))
        self.receiver_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)  # set to reuse socket
        self.sender_sock = socket(AF_INET, SOCK_DGRAM)  # Aodv sender socket
        self.sender_sock.bind(('localhost', 0))
        self.sender_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)  # set to reuse socket
        self.sender_port = self.sender_sock.getsockname()[1]  # getting the randomly assigned port to sender
        self.receiver_port = self.receiver_sock.getsockname()[1]  # getting the randomly assigned port to receiver
        self.neighbors = dict()  # list of neighbours
        self.routing_table = dict()  # list of routes
        self.message_box = dict()  # list of messages
        self.rreq_id_list = dict()  # list of RREQs sent
        self.rreq_id = 0  # RREQ id number
        self.seq_no = 0  # sequence number
        self.pending_msg_q = []  # list of pending messages
        self.prompt = "\nAODV-Node " + self.node_name + " Enter Commands> "

        # Setup logging
        self.log_file = "aodv_log_" + self.node_name
        format_msg = "%(asctime)s - %(message)s"
        logging.basicConfig(filename=self.log_file, level=logging.DEBUG, format=format_msg)

        # start the AODV receiver on a seperate thread
        t = threading.Thread(target=self.receiver)
        t.daemon = True
        t.start()

    # aodv receiver that receives packets from network, calls appropriate func and runs on a separate thread
    def receiver(self):

        while True:
            # When we get a message from the network
            message, _ = self.receiver_sock.recvfrom(200)
            # message = message.decode('utf-8')
            message_parts = message.split('|')

            message_type = message_parts[0]
            if message_type == AODV_HELLO_TYPE:
                self.process_hello_message(message_parts)
            elif message_type == USER_MESSAGE:
                self.receive_user_message(message_parts)
            elif message_type == AODV_RREQ_MESSAGE:
                self.process_rreq_message(message_parts)
            elif message_type == AODV_RREP_MESSAGE:
                self.process_rrep_message(message_parts)
            elif message_type == AODV_RRER_MESSAGE:
                self.process_rerr_message(message_parts)

    # Take the neighbor set for the current node from the user
    def add_neighbors(self, addresses, create_new_route):

        for address in addresses.split(' '):
            # Update the routing table. Setup direct routes for each added neighbor.
            node_name, port = address.split(':')
            if create_new_route:
                dest = str(node_name)
                dest_port = str(port)
                nh = str(node_name)
                nh_port = str(port)
                seq = '1'
                hop_count = '1'
                status = 'Active'

                self.routing_table[address] = {'Destination-name': dest,
                                               'Destination-Port': dest_port,
                                               'Next-Hop': nh,
                                               'Next-Hop-Port': nh_port,
                                               'Seq-No': seq,
                                               'Hop-Count': hop_count,
                                               'Status': status}

            self.restart_route_timer(self.routing_table[address], create_new_route)

            # Start a timer to start sending hello messages periodically
            # hello_timer = Timer(AODV_HELLO_INTERVAL, self.send_hello_to_neighbour, [address])
            timeout_timer = Timer(AODV_HELLO_TIMEOUT, self.handle_neighbor_timeout, [port])
            self.neighbors[port] = {'Neighbor': node_name, 'Port': port, 'Timer-Callback': timeout_timer}
            timeout_timer.start()
            self.send_hello_to_neighbour(address)
            # hello_timer.start()

            print("\n...." + node_name + " added as Neighbor....")

    # Create / Restart the lifetime timer for the given route
    def restart_route_timer(self, route, create):
        if not create:
            timer = route['Lifetime']
            timer.cancel()

        timer = Timer(AODV_ACTIVE_ROUTE_TIMEOUT,
                      self.handle_route_timeout, [route])
        route['Lifetime'] = timer
        route['Status'] = 'Active'
        timer.start()

    # Send hello message to neighbour
    def send_hello_to_neighbour(self, address):
        node_name, port = address.split(':')
        try:
            # Send message to neighbor and wait for reply
            message_type = AODV_HELLO_TYPE
            sender = self.node_name
            receiving_port = str(self.receiver_port)
            message_data = "Hello message from " + str(self.node_name)
            message = message_type + "|" + sender + "|" + receiving_port + "|" + message_data
            self.sender_sock.sendto(message, 0, ('localhost', int(port)))
            logging.debug(
                "['" + message_type + "', '" + sender + "', " + "Sending hello message to " + str(node_name) + "']")

        except Exception:
            traceback.print_exc()
            print("Error Neighbor not Reachable: " + node_name)

    # Handle neighbor timeouts
    def handle_neighbor_timeout(self, neighbor_port):

        # Update the routing table. Mark the route as inactive.
        address = self.neighbors[neighbor_port]['Neighbor'] + ':' + neighbor_port
        route = self.routing_table[address]
        route['Status'] = 'Inactive'
        dest = route['Destination-name']
        dest_seq_no = int(route['Seq-No'])

        # Log a message
        logging.debug("aodv_process_neighbor_timeout: " + dest + " went down")

        # Send an RERR to all the neighbors
        self.send_rerr(dest + ':' + neighbor_port, dest_seq_no)

        # Try to repair the route
        dest_seq_no += 1
        self.send_rreq(dest + ':' + neighbor_port, dest_seq_no)

    # Handle route timeouts
    def handle_route_timeout(self, route):

        # Remove the route from the routing table
        key = route['Destination-name'] + ':' + route['Destination-Port']
        self.routing_table.pop(key)

        #
        # If the destination is a neighbor, remove it from the neighbor table
        # as well
        #
        if key in self.neighbors:
            self.neighbors.pop(key)

        logging.debug("aodv_process_route_timeout: removing " + key + " from the routing table.")

    # Generate and send a Route Error message
    def send_rerr(self, destination, dest_seq_no):
        # Construct the RERR message
        message_type = AODV_RRER_MESSAGE
        sender = self.node_name + ':' + str(self.receiver_port)
        dest_count = '1'
        dest_seq_no = dest_seq_no + 1
        message = message_type + "|" + sender + "|" + dest_count + "|" + destination + "|" + str(dest_seq_no)

        # Now broadcast the RRER message
        for port in self.neighbors.keys():
            self.aodv_send(self.neighbors[port]['Neighbor'], int(port), message)

        logging.debug("['" + message_type + "', 'Sending RERR for " + destination + "']")

    # Send a message
    def aodv_send(self, destination, destination_port, message):
        try:
            self.sender_sock.sendto(message, 0, ('localhost', destination_port))
        except Exception:
            traceback.print_exc()
            print("Error sending message to " + destination)

    # Broadcast an RREQ message for the given destination
    def send_rreq(self, destination_address, destination_seq_no):

        # Increment our sequence number
        self.seq_no = self.seq_no + 1

        # Increment the RREQ_ID
        self.rreq_id = self.rreq_id + 1

        # Construct the RREQ packet
        message_type = AODV_RREQ_MESSAGE
        sender_address = self.node_name + ':' + str(self.receiver_port)
        hop_count = 0
        rreq_id = self.rreq_id
        dest = destination_address
        dest_seq_no = destination_seq_no
        orig = sender_address
        orig_seq_no = self.seq_no
        message = message_type + "|" + sender_address + "|" + str(hop_count) + "|" + str(rreq_id) + "|" + str(
            dest) + "|" + str(dest_seq_no) + "|" + str(orig) + "|" + str(orig_seq_no)

        # Broadcast the RREQ packet to all the neighbors
        for port in self.neighbors.keys():
            dest_neighbour = self.neighbors[port]['Neighbor']
            self.aodv_send(dest_neighbour, int(port), message)
            logging.debug("['" + message_type + "', 'Broadcasting RREQ to " + dest + "']")

        # Buffer the RREQ_ID for PATH_DISCOVERY_TIME. This is used to discard duplicate RREQ messages
        if sender_address in self.rreq_id_list.keys():
            per_node_list = self.rreq_id_list[sender_address]
        else:
            per_node_list = dict()
        path_discovery_timer = Timer(AODV_PATH_DISCOVERY_TIME,
                                     self.handle_process_path_discovery_timeout,
                                     [self.node_name, rreq_id])
        per_node_list[rreq_id] = {'RREQ_ID': rreq_id,
                                  'Timer-Callback': path_discovery_timer}
        self.rreq_id_list[sender_address] = {'Node': self.node_name,
                                             'RREQ_ID_List': per_node_list}
        path_discovery_timer.start()

    # Send an RREP message back to the RREQ originator
    def send_rrep(self, hop_count, dest_address, dest_seq_no, orig_address, nh_node_name, nh_port_to_orig):
        #
        # Check if we are the destination in the RREP. If not, use the
        # parameters passed.
        #
        sender_address = self.node_name + ':' + str(self.receiver_port)

        if sender_address == dest_address:
            # Increment the sequence number and reset the hop count
            self.seq_no = self.seq_no + 1
            dest_seq_no = self.seq_no
            hop_count = 0

        # Construct the RREP message
        message_type = AODV_RREP_MESSAGE
        message = message_type + "|" + sender_address + "|" + str(hop_count) + "|" + str(dest_address) + "|" + str(
            dest_seq_no) + "|" + str(orig_address)

        # Now send the RREP to the RREQ originator along the next-hop
        self.aodv_send(nh_node_name, int(nh_port_to_orig), message)
        logging.debug(
            "['" + message_type + "', 'Sending RREP for " + dest_address + " to " + nh_node_name + " via " + nh_node_name + "']")

    # Handle Path Discovery timeouts
    def handle_process_path_discovery_timeout(self, node, rreq_id):

        # Remove the buffered RREQ_ID for the given node
        if node in self.rreq_id_list.keys():
            node_list = self.rreq_id_list[node]
            per_node_rreq_id_list = node_list['RREQ_ID_List']
            if rreq_id in per_node_rreq_id_list.keys():
                per_node_rreq_id_list.pop(rreq_id)

    # Process incoming hello messages
    def process_hello_message(self, message):
        logging.debug(message)
        sender_name = message[1]
        sender_port = message[2]
        sender_address = sender_name + ":" + sender_port

        # Get the sender's ID and restart its neighbor liveness timer
        try:
            if sender_port in self.neighbors.keys():
                neighbor = self.neighbors[sender_port]
                neighbor['Timer-Callback'].cancel()
                timer = Timer(AODV_HELLO_TIMEOUT, self.handle_neighbor_timeout, [sender_port])
                neighbor['Timer-Callback'] = timer
                timer.start()

                # Restart the lifetime timer
                route = self.routing_table[sender_address]
                self.restart_route_timer(route, False)

            else:
                #
                # We come here when we get a hello message from a node that
                # is not there in our neighbor list. This happens when a
                # node times out and comes back up again. Add the node to
                # our neighbor table.
                #

                # Update the routing table as well
                if sender_address in self.routing_table.keys():
                    self.add_neighbors(sender_address, False)

                else:
                    self.add_neighbors(sender_address, True)

        except KeyError:
            # This neighbor has not been added yet. Ignore the message.
            pass

    # Display the routing table for the current node
    def show_routing_table(self):
        print("")
        print("There are " + str(len(self.routing_table)) + " active route(s) in the routing-table")
        print("")

        print("Destination     Next-Hop     Seq-No     Hop-Count     Status")
        print("------------------------------------------------------------")
        for r in self.routing_table.values():
            print(str(r['Destination-name']) + "              " + str(r['Next-Hop']) + "           " + str(
                r['Seq-No']) + "          " + str(r['Hop-Count']) + "             " + str(r['Status']))
        print("")

    # Process an incoming RREQ message
    def process_rreq_message(self, message):

        # Extract the relevant parameters from the message
        sender_address = message[1]
        sender_name, sender_port = sender_address.split(':')
        hop_count = int(message[2]) + 1
        message[2] = str(hop_count)
        rreq_id = int(message[3])
        dest_address = message[4]
        dest_seq_no = int(message[5])
        orig_address = message[6]
        orig_name, orig_port = orig_address.split(':')
        orig_seq_no = int(message[7])

        logging.debug("['" + message[0] + "', 'Received RREQ to " + dest_address + " from " + sender_address + "']")

        # Discard this RREQ if we have already received this before
        if (orig_address in self.rreq_id_list.keys()):
            node_list = self.rreq_id_list[orig_address]
            per_node_rreq_id_list = node_list['RREQ_ID_List']
            if rreq_id in per_node_rreq_id_list.keys():
                logging.debug("['RREQ_MESSAGE', 'Ignoring duplicate RREQ (" + orig_name + ", " + str(
                    rreq_id) + ") from " + sender_name + "']")
                return

        # This is a new RREQ message. Buffer it first
        if (orig_address in self.rreq_id_list.keys()):
            per_node_list = self.rreq_id_list[orig_address]
        else:
            per_node_list = dict()
        path_discovery_timer = Timer(AODV_PATH_DISCOVERY_TIME, self.handle_process_path_discovery_timeout,
                                     [orig_address, rreq_id])
        per_node_list[rreq_id] = {'RREQ_ID': rreq_id, 'Timer-Callback': path_discovery_timer}
        self.rreq_id_list[orig_address] = {'Node': self.node_name, 'RREQ_ID_List': per_node_list}
        path_discovery_timer.start()

        #
        # Check if we have a route to the source. If we have, see if we need
        # to update it. Specifically, update it only if:
        #
        # 1. The destination sequence number for the route is less than the
        #    originator sequence number in the packet
        # 2. The sequence numbers are equal, but the hop_count in the packet
        #    + 1 is lesser than the one in routing table
        # 3. The sequence number in the routing table is unknown
        #
        # If we don't have a route for the originator, add an entry

        if orig_address in self.routing_table.keys():
            # TODO update lifetime timer for this route
            route = self.routing_table[orig_address]
            if (int(route['Seq-No']) < orig_seq_no):
                route['Seq-No'] = orig_seq_no
            elif int(route['Seq-No']) == orig_seq_no and int(route['Hop-Count']) > hop_count:
                route['Hop-Count'] = hop_count
                route['Next-Hop'] = sender_name
                route['Next-Hop-Port'] = sender_port
            elif (int(route['Seq-No']) == -1):
                route['Seq-No'] = orig_seq_no

            self.restart_route_timer(route, False)

        else:
            # TODO update lifetime timer for this route
            self.routing_table[orig_address] = {'Destination-name': str(orig_name),
                                                'Destination-Port': str(orig_port),
                                                'Next-Hop': str(sender_name),
                                                'Next-Hop-Port': str(sender_port),
                                                'Seq-No': str(orig_seq_no),
                                                'Hop-Count': str(hop_count),
                                                'Status': 'Active'}
            self.restart_route_timer(self.routing_table[orig_address], True)

        #
        # Check if we are the destination. If we are, generate and send an
        # RREP back.
        #
        if (self.node_name + ':' + str(self.receiver_port) == dest_address):
            self.send_rrep(0, dest_address, 0, orig_address, sender_name, sender_port)
            return

        #
        # We are not the destination. Check if we have a valid route
        # to the destination. If we have, generate and send back an
        # RREP.
        #
        if (dest_address in self.routing_table.keys()):
            # Verify that the route is valid and has a higher seq number
            route = self.routing_table[dest_address]
            status = route['Status']
            route_dest_seq_no = int(route['Seq-No'])
            if (status == "Active" and route_dest_seq_no >= dest_seq_no):
                self.send_rrep(int(route['Hop-Count']), dest_address, route_dest_seq_no, orig_address, sender_name,
                               sender_port)
                return
        else:
            # Rebroadcast the RREQ
            self.aodv_forward_rreq(message)

    #
    # Rebroadcast an RREQ request (Called when RREQ is received by an
    # intermediate node)
    #
    def aodv_forward_rreq(self, message):
        msg = message[0] + "|" + self.node_name + ':' + str(self.receiver_port) + "|" + message[2] + "|" + message[
            3] + "|" + \
              message[4] + "|" + \
              message[5] + "|" + message[6] + "|" + message[7]
        for port in self.neighbors:
            self.aodv_send(self.neighbors[port]['Neighbor'], int(port), msg)
            logging.debug("['" + message[0] + "', 'Rebroadcasting RREQ to " + message[4] + "']")

    # Process an incoming RREP message
    def process_rrep_message(self, message):
        # Extract the relevant fields from the message
        message_type = message[0]
        sender_address = message[1]
        sender_name, sender_port = sender_address.split(':')
        hop_count = int(message[2]) + 1
        message[2] = str(hop_count)
        dest_address = message[3]
        dest_name, dest_port = dest_address.split(':')
        dest_seq_no = int(message[4])
        orig_address = message[5]

        logging.debug("['" + message_type + "', 'Received RREP for " + dest_address + " from " + sender_address + "']")

        # Check if we originated the RREQ. If so, consume the RREP.
        if (self.node_name + ':' + str(self.receiver_port) == orig_address):
            #
            # Update the routing table. If we have already got a route for
            # this destination, compare the hop count and update the route
            # if needed.
            #
            if (dest_address in self.routing_table.keys()):
                route = self.routing_table[dest_address]
                route_hop_count = int(route['Hop-Count'])
                if (route_hop_count > hop_count):
                    route['Hop-Count'] = str(hop_count)
                    self.restart_route_timer(self.routing_table[dest_address], False)
            else:
                self.routing_table[dest_address] = {'Destination-name': dest_address,
                                                    'Destination-Port': dest_port,
                                                    'Next-Hop': sender_name,
                                                    'Next-Hop-Port': sender_port,
                                                    'Seq-No': str(dest_seq_no),
                                                    'Hop-Count': str(hop_count),
                                                    'Status': 'Active'}
                self.restart_route_timer(self.routing_table[dest_address], True)

            # Check if we have any pending messages to this destination
            for m in self.pending_msg_q:
                msg = m.split('|')
                d = msg[2]
                if (d == dest_address):
                    # Send the pending message and remove it from the buffer
                    next_hop = sender_name
                    next_hop_port = dest_port
                    self.aodv_send(next_hop, int(next_hop_port), m)
                    logging.debug(
                        "['USER_MESSAGE', '" + msg[1] + " to " + msg[2] + " via " + next_hop + "', '" + msg[3] + "']")
                    print("Message sent")

                    self.pending_msg_q.remove(m)

        else:
            #
            # We need to forward the RREP. Before forwarding, update
            # information about the destination in our routing table.
            #
            if (dest_address in self.routing_table.keys()):
                route = self.routing_table[dest_address]
                route['Status'] = 'Active'
                route['Seq-No'] = str(dest_seq_no)
                self.restart_route_timer(route, False)
            else:
                self.routing_table[dest_address] = {'Destination-name': dest_name,
                                                    'Destination-Port': dest_port,
                                                    'Next-Hop': sender_name,
                                                    'Next-Hop-Port': sender_port,
                                                    'Seq-No': str(dest_seq_no),
                                                    'Hop-Count': str(hop_count),
                                                    'Status': 'Active'}
                self.restart_route_timer(self.routing_table[dest_address], True)
                # TODO update/add a lifetime timer for the route

            # Now lookup the next-hop for the source and forward it
            route = self.routing_table[orig_address]
            next_hop = route['Next-Hop']
            next_hop_port = int(route['Next-Hop-Port'])
            self.forward_rrep(message, next_hop, next_hop_port)

    #
    # Forward an RREP message (Called when RREP is received by an
    # intermediate node)
    #
    def forward_rrep(self, message, next_hop, next_hop_port):
        msg = message[0] + "|" + self.node_name + ':' + str(self.receiver_port) + "|" + message[2] + "|" + message[
            3] + "|" + \
              message[4] + "|" + message[5]
        self.aodv_send(next_hop, next_hop_port, msg)
        logging.debug("['" + message[0] + "', 'Forwarding RREP for " + message[5] + " to " + next_hop + "']")

    # Process an incoming RERR message
    def process_rerr_message(self, message):
        # Extract the relevant fields from the message
        message_type = message[0]
        sender_address = message[1]
        dest_address = message[3]
        dest_seq_no = int(message[4])

        if (self.node_name + ':' + str(self.receiver_port) == dest_address):
            return

        logging.debug("['" + message_type + "', 'Received RERR for " + dest_address + " from " + sender_address + "']")

        #
        # Take action only if we have an active route to the destination with
        # sender as the next-hop
        #
        if (dest_address in self.routing_table.keys()):
            route = self.routing_table[dest_address]
            if (route['Status'] == 'Active' and route['Next-Hop'] + ':' + route['Next-Hop-Port'] == sender_address):
                # Mark the destination as inactive
                route['Status'] = "Inactive"

                # Forward the RERR to all the neighbors
                self.forward_rerr(message)
            else:
                logging.debug(
                    "['" + message_type + "', 'Ignoring RERR for " + dest_address + " from " + sender_address + "']")

    # Forward a Route Error message
    def forward_rerr(self, message):
        msg = message[0] + "|" + self.node_name + ':' + str(self.receiver_port) + "|" + message[2] + "|" + message[
            3] + "|" + \
              message[4]
        for port in self.neighbors.keys():
            self.aodv_send(self.neighbors[port]['Neighbor'], int(port), msg)

        logging.debug("['" + message[0] + "', 'Forwarding RERR for " + message[3] + "']")

    # Receive incoming application message
    def receive_user_message(self, message):

        # Get the message contents, sender and receiver
        sender = message[1]
        receiver = message[2]
        msg = message[3]

        # Check if the message is for us
        if (receiver == self.node_name + ':' + str(self.receiver_port)):

            # Add the message to the message box
            self.message_box[msg] = {'Sender': sender, 'Message': msg}

            # Log the message and notify the user
            logging.debug(message)
            print("New message arrived. Issue 'show_messages' to see the contents")

        else:
            #
            # Forward the message by looking up the next-hop. We should have a
            # route for the destination.
            #
            # TODO update lifetime for the route
            route = self.routing_table[receiver]
            next_hop = route['Next-Hop']
            next_hop_port = int(route['Next-Hop-Port'])
            self.restart_route_timer(route, False)
            message = message[0] + "|" + message[1] + "|" + message[2] + "|" + message[3]
            self.aodv_send(next_hop, next_hop_port, message)
            logging.debug("['USER_MESSAGE', '" + sender + " to " + receiver + "', " + msg + "']")

    # Send a message to a peer
    def send_user_message(self, message):

        # Get the command sent by the listener thread / tester process
        command = message.split('|')
        source_address = self.node_name + ':' + str(self.receiver_port)
        dest_address = command[0]
        message_data = command[1]
        dest_name, dest_port = dest_address.split(':')

        # Format the message
        message_type = USER_MESSAGE
        message = message_type + "|" + source_address + "|" + dest_address + "|" + message_data

        # First check if we have a route for the destination
        if dest_address in self.routing_table.keys():
            # Route already present. Get the next-hop for the destination.
            destination = self.routing_table[dest_address]

            if (destination['Status'] == 'Inactive'):
                # We don't have a valid route. Broadcast an RREQ.
                self.send_rreq(dest_address, destination['Seq-No'])
            else:
                next_hop = destination['Next-Hop']
                next_hop_port = destination['Next-Hop-Port']
                self.aodv_send(next_hop, int(next_hop_port), message)
                # TODO: update lifetime here as the route was used
                self.restart_route_timer(destination, False)
                logging.debug(
                    "['USER_MESSAGE', '" + self.node_name + " to " + dest_name + " via " + next_hop + "', '" + message_data + "']")
                print("Message sent")
        else:
            # Initiate a route discovery message to the destination
            self.send_rreq(dest_address, -1)
            print("Message Waiting in Que....")
            # Buffer the message and resend it once RREP is received
            self.pending_msg_q.append(message)

    # Return the buffered messages back to the node
    def show_messages(self):
        print("")
        print("There are " + str(len(self.message_box)) + " message(s) in the message-box")
        print("")

        print("Sender\t\tMessage")
        print("-------------------------------------------")
        for m in self.message_box.values():
            print(m['Sender'] + "\t" + m['Message'])
        print("")

    # Delete the messages buffered for the given node
    def delete_messages(self):
        # Remove all the messages from the message box
        self.message_box.clear()
        print("Message box has been cleared")
