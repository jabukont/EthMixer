import multiprocessing
from decimal import Decimal
from mnemonic import Mnemonic
from web3 import Web3
import random
import time
import zmq
import json
from multiprocessing import Process

ganache_url = "http://127.0.0.1:7545"
web3 = Web3(Web3.HTTPProvider(ganache_url))
pool = web3.eth.accounts[0]
data = json.load(open('data.json'))
settings = json.load(open('inputs.json'))
l = multiprocessing.Lock()


def send(source, dest, privateKey, amount):
    l.acquire()
    account_1 = source  # Fill me in
    account_2 = dest  # Fill me in
    private_key = privateKey  # Fill me in
    nonce = web3.eth.getTransactionCount(account_1)
    tx = {
        'nonce': nonce,
        'to': account_2,
        'value': web3.toWei(amount, 'ether'),
        'gas': settings['gas_price'],
        'gasPrice': web3.toWei('50', 'gwei'),
    }
    signed_tx = web3.eth.account.signTransaction(tx, private_key)
    tx_hash = None
    while tx_hash is None:
        try:
            # connect
            tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)
        except ValueError:
            tx = {
                'nonce': web3.eth.getTransactionCount(account_1),
                'to': account_2,
                'value': web3.toWei(amount, 'ether'),
                'gas': settings['gas_price'],
                'gasPrice': web3.toWei('50', 'gwei'),
            }
            signed_tx = web3.eth.account.signTransaction(tx, private_key)
    l.release()


def createWallet():
    mnemo = Mnemonic("english")
    words = mnemo.generate(strength=256)
    seed = mnemo.to_seed(words, passphrase="")
    account = web3.eth.account.privateKeyToAccount(seed[:32])
    private_key = account.privateKey
    public_key = account.address
    return (public_key, private_key)


def worker(address, priv_key, dest):
    context = zmq.Context()
    consumer_sender = context.socket(zmq.PUSH)
    consumer_sender.connect("tcp://127.0.0.1:5559")
    # print('waiting for balance')
    while (web3.eth.getBalance(address) == 0):
        pass
    total = web3.fromWei(web3.eth.getBalance(address) - 2000000 * web3.toWei('50', 'gwei'), 'ether')
    # print(total)
    fee = random.uniform(.97, 1)
    # print(Decimal(fee))
    result = {"dest": str(dest), "total": str(total * Decimal(fee))}
    consumer_sender.send_json(result)
    send(address, pool, priv_key, total)
    return total


def server(port):
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:%s" % port)
    while True:
        dest = socket.recv()
        dest = dest.decode("utf-8")
        wallet = createWallet()
        socket.send_string(str(wallet[0]))
        # p = Process(target=waitForbalance, args=(wallet[0],wallet[1],dest))
        # p.start()
        worker(wallet[0], wallet[1], dest)
        time.sleep(3)


def client(port, source, dest, amount):
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://localhost:%s" % port)
    web3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))
    account_1 = str(web3.eth.accounts[dest])  # Fill me in
    socket.send_string(account_1)
    message = socket.recv()
    message = message.decode("utf-8")

    def send(dest):
        account_2 = str(dest)  # Fill me in
        private_key = data['private_keys'][web3.eth.accounts[source].lower()]  # Fill me in
        # print(private_key)
        nonce = web3.eth.getTransactionCount(web3.eth.accounts[source])
        tx = {
            'nonce': nonce,
            'to': account_2,
            'value': web3.toWei(amount, 'ether'),
            'gas': settings['gas_price'],
            'gasPrice': web3.toWei('50', 'gwei'),
        }
        signed_tx = web3.eth.account.signTransaction(tx, private_key)
        tx_hash = None
        while tx_hash is None:
            try:
                # connect
                tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)
            except ValueError:
                tx = {
                    'nonce': web3.eth.getTransactionCount(web3.eth.accounts[source]),
                    'to': account_2,
                    'value': web3.toWei(amount, 'ether'),
                    'gas': settings['gas_price'],
                    'gasPrice': web3.toWei('50', 'gwei'),
                }
                signed_tx = web3.eth.account.signTransaction(tx, private_key)

    send(message)


def timer():
    context = zmq.Context()
    consumer_sender = context.socket(zmq.PUSH)
    consumer_sender.connect("tcp://127.0.0.1:5559")
    starttime = time.time()
    while True:
        if ((time.time() - starttime) >= settings['pool_holding_time']):
            data = {"send": "test"}
            consumer_sender.send_json(data)
            starttime = time.time()


def result_collector():
    context = zmq.Context()
    results_receiver = context.socket(zmq.PULL)
    results_receiver.bind("tcp://127.0.0.1:5559")
    orders = []
    while True:
        result = results_receiver.recv_json()
        if ('send' in result):
            # print(json.dumps(orders, indent=1))
            for order in orders:
                # print(order)
                send(web3.eth.accounts[0], order['dest'], data['private_keys'][web3.eth.accounts[0].lower()],
                     order['total'])
            orders = []
        else:
            orders.append(result)


def getTransactions(start, end):
    with open("transactions.txt", "w") as f:
        for x in range(start, end):
            block = web3.eth.getBlock(x, True)
            for transaction in block.transactions:
                f.write("Source: " + str(transaction['from']) + " Dest: " + str(transaction['to']) + " Amount: " + str(
                    transaction['value']) + '\n')
    f.close()
    print(f"Transactions from blocks {start} through {end} in transactions.txt")


if __name__ == '__main__':
    starting_blocknumber = web3.eth.blockNumber
    start = time.time()
    Process(target=result_collector).start()
    Process(target=timer).start()
    port = 6000
    while (time.time() - start <= settings['sim_duration']):
        source = random.randrange(1, len(web3.eth.accounts), 1)
        dest = random.randrange(1, len(web3.eth.accounts), 1)
        while (dest == source):
            dest = random.randrange(1, len(web3.eth.accounts), 1)
        if (random.uniform(0, 1) > settings["percent_noise:"]):
            Process(target=server, args=(port,)).start()
            Process(target=client, args=(port, source, dest, Decimal(
                random.uniform(settings['eth_sent_per_transaction'][0],
                               settings['eth_sent_per_transaction'][1])))).start()
            port = port + 1
        else:
            try:
                send(web3.eth.accounts[source], web3.eth.accounts[dest],
                     data['private_keys'][web3.eth.accounts[source].lower()], Decimal(
                        random.uniform(settings['eth_sent_per_transaction'][0],
                                       settings['eth_sent_per_transaction'][1])))
            except ValueError:
                pass
        time.sleep(settings['transaction_speed'])
    if settings['total'] == 1:
        starting_blocknumber = 0
    getTransactions(starting_blocknumber, web3.eth.blockNumber)
