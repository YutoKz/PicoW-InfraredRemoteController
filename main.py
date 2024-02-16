from umqtt.simple import MQTTClient
from machine import Pin, PWM
import time
from wifi import connect

ir = PWM(Pin(17, Pin.OUT))
f = 38000
ir.freq(f)
dty = 0x5555

#　必要に応じ調整　今回は35が適当
adj = 35

# MQTT
MQTT_BROKER = "192.168.3.6"
MQTT_TOPIC = "koizumi"

shared_data = [0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0]
    
def send_data(data):
    #　はじめのやつ
    # デューティー比1/3がHIGHのPWM信号を送信（adj回分）
    for i in range(1, 18*adj):
        ir.duty_u16(dty)
            
    # LOWのPWM信号を送信（3×adj回分）
    for i in range(1, 9*adj):
        ir.duty_u16(0)

    # 16bitのコードを読み込む
    for bit in data:
       
        # コードの値が「1」のときの処理
        if(bit == 1):
        
            # デューティー比1/3がHIGHのPWM信号を送信（adj回分）
            for i in range(1, 1*adj):
                ir.duty_u16(dty)
            
            # LOWのPWM信号を送信（3×adj回分）
            for i in range(1, 3*adj):
                ir.duty_u16(0)
         
        # コードの値が「0」のときの処理
        else:
            
            # デューティー比1/3がHIGHのPWM信号を送信（adj回分）
            for i in range(1, 1*adj):
                ir.duty_u16(dty)
            
            # LOWのPWM信号を送信（7×adj回分）
            for i in range(1, 1*adj):
                ir.duty_u16(0)
    
    # ストップビット（データの終端を示す信号）
    for l in range(1,1*adj):
        ir.duty_u16(dty)

    # トレーラー（通信の終わりを示す信号）
    for l in range(1,1*adj):
        for i in range(1,85):
            ir.duty_u16(0)
            
    print(f'send {data}')
        
def callback(topic, msg):
    print(f'received {msg}')
    
    if msg == b"junnokuri":
        data = shared_data + [0, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1]
    elif msg == b"up":
        data = shared_data + [1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1]
    elif msg == b"down":
        data = shared_data + [0, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1]
    elif msg == b"30minoff":
        data = shared_data + [1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
    elif msg == b"60minoff":
        data = shared_data + [0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1]
    elif msg == b"kaijo":
        data = shared_data + [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]
    elif msg == b"shoutou":
        data = shared_data + [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1]
    else:
        data = shared_data
    
    send_data(data)

ip = connect()
print(f'connected on {ip}')

# MQTT
client = MQTTClient("controller", MQTT_BROKER)
client.set_callback(callback)

# 試み
connection_flag = False
while connection_flag is False:
    try:
        client.connect()
        print("Connected to Broker")
        connection_flag = True
    except OSError as e:
        print("Couldn't connect to Broker:", e)
        connection_flag = False



#client.connect()
client.subscribe(MQTT_TOPIC)
print("connected to client")

while True:
    client.wait_msg()
    
    

