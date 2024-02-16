# アナログ－デジタル変換のライブラリを読み込む
from machine import ADC

# 時間関連のライブラリを読み込む
import utime

# ADC0（31Pin）をアナログ－デジタル変換の入力ピンに設定
adc = ADC(0)

# センサーの状態（HIGHか？LOWか？）
st = 1

# カウンタ
cnt = 0

# 稼働時間の計測開始
start = utime.ticks_us()

# 永久ループ
while True:
    
        # read_u16() ・・・アナログ値を読込み［0-65535］の整数を返す関数
        # 16bit・2進数の最大値：1111111111111111 ⇒ 10進数の最大値：65535
        # 電圧の最大値3.3Vを「65535」に置き換え
        sens = adc.read_u16()* (3.3 / 65535)
        
        # 赤外線を受信している（センサーにかかる電圧が1Vより小さいとき）
        if(sens < 1.0):
             
            # センサーの状態がLOW→HIGHに切り替わった瞬間の処理
            if (st == 1):
                
                # センサーの状態がLOWを示す
                st = 0
                
                # カウントアップ
                cnt += 1
                
                # 稼働時間の計測終了
                end = utime.ticks_us()
                
                # 稼働時間の開始と終了の差を表示
                tics = utime.ticks_diff(start,end)
                
                # 計測終了時間を次の稼働時間の開始時間に設定
                start = end
                   
                # 周期の計測結果を出力
                print(tics)

        # 赤外線を受信していない（センサーにかかる電圧が1Vより大きいとき）
        else:
            
            # センサーの状態がHIGH→LOWに切り替わった瞬間の処理
            if (st == 0):
                
                # センサーの状態がHIGHを示す
                st = 1
                
                # カウントアップ
                cnt += 1
                
                # 稼働時間の計測終了
                end = utime.ticks_us()
                
                # 稼働時間の開始と終了の差を表示
                tics = utime.ticks_diff(end, start)
                
                # 計測終了時間を次の稼働時間の開始時間に設定
                start = end
                
                # 周期の計測結果を出力
                print(tics)

        # 100個のデータを取得したら計測終了
        if (cnt >= 100):
            
            # 永久ループを抜ける
            break
