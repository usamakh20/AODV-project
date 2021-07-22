# Imports
import Aodv


# Class Definition
class app():
    # Constructor
    def __init__(self, id):
        self.node_id = id
        self.command = ""
        self.aodv = Aodv.Aodv(id)

    # Set the Node ID
    def set_node_id(self, id):
        self.node_id = id

    # Called when user issues help. Dump the list of available commands.
    def help(self):
        print("The following list of commands are available:")
        print("send_message    : Send a message to a peer node")
        print("show_messages   : View the messages received so far")
        print("delete_messages : Delete all the messages in the message box")
        print("show_routes     : Display the routing table for the AODV node")
        print("add_neighbours  : Add neighbors to the current AODV node")

    # Delete all the messages received so far
    def delete_messages(self):
        self.aodv.delete_messages()

    # Send a message to a peer
    def send_message(self):

        # Get the message details from the user
        message = input("Enter the message to send: ")
        node_addr = input("Enter the destination address (name:port): ")

        message = node_addr + "|" + message
        # message_bytes = message
        self.aodv.send_user_message(message)

    # Display the messages sent to this node by other nodes
    def show_messages(self):
        self.aodv.show_messages()

    # Display the routing table
    def show_routes(self):
        self.aodv.show_routing_table()

    # Default routine called when invalid command is issued. Do nothing.
    def default(self):
        if (len(self.command) == 0):
            pass
        else:
            print("Invalid Command")

    # Take the neighbour ports and add as direct neighbour to current node
    def add_neighbors(self):
        neighbor_ports = input("Enter the neighbor addresses (name:port), separated by a space: ")
        self.aodv.add_neighbors(neighbor_ports, True)

    # Thread start routine
    def run(self):

        # Set the prompt
        prompt = "AODV-Node " + self.node_id + " Enter Commands> "
        commands = {'help': self.help,
                    'delete_messages': self.delete_messages,
                    'send_message': self.send_message,
                    'show_messages': self.show_messages,
                    'show_routes': self.show_routes,
                    'add_neighbours': self.add_neighbors}
        print(self.node_id + " listening at port: " + str(self.aodv.receiver_port) + '........')

        # Listen indefinitely for user inputs and pass them to the AODV protocol handler thread
        while (True):
            command = input(prompt)
            self.command = command
            commands.get(command, self.default)()


# End of File

if __name__ == '__main__':
    # Get the arguments passed by the driver program
    node_id = input("Enter node name: ")

    # Instantiate the AODV app and call its run method
    AODV_app = app(node_id)
    AODV_app.run()
