# PicoW-InfraredRemoteController

Raspberry Pi Pico Wで、元のエアコンリモコンの赤外線信号を学習し、スマホから再送するMicroPythonプロジェクトです。自宅ではWi-Fi、外出先では自宅へのVPN接続を使います。

**対象エアコンの型番・回路・学習信号はまだ未確認です。実装とホスト上のテストは用意していますが、実機での動作確認は必要です。** 架空のエアコン信号は同梱していません。

## できること

- 「冷房26℃・風量自動」「暖房22℃」「停止」など、学習した設定をブラウザから送信。
- 操作画面から信号を学習・保存・削除。保存後の再起動でもデータを保持。
- PIOによる搬送波と送信時間の制御。元コードの `adj` によるループ時間調整は不要。
- 長い信号や複数フレームを記録（最大2047パルス、合計2秒、32プリセット）。
- アクセスキーによるAPI認証、POSTによる操作、短時間の連打抑制。
- DHCPで接続し、Wi-Fi切断後は再試行。起動・再接続時には赤外線を送信しない。

多くのエアコンリモコンは温度・モード・風量などの状態全体を送ります。この実装はその**生波形を丸ごと保存するプリセット方式**です。未学習の温度や風量を計算して生成する機能はありません。機種固有のエンコーダーを追加するには、エアコンとリモコンの型番・信号仕様が必要です。

## 必要な機器・配線

| 機器 | 条件 |
| --- | --- |
| Raspberry Pi Pico W / WH | RP2040、MicroPython公式Pico W用ファームウェア。v1.26.0以降を想定 |
| 赤外線送信部 | 3.3 V GPIO入力に対応する、active-highのトランジスター駆動回路/モジュール |
| 赤外線受信部 | 3.3 Vで動作し、出力が3.3 V以下のactive-low復調モジュール。搬送波に合うもの |
| 元のエアコンリモコン | 赤外線式。希望する設定の信号を学習するために使用 |
| USBケーブル・電源 | 書き込み時はデータ通信対応ケーブル。運用時は常時給電 |
| 2.4 GHz Wi-Fi | Pico Wとスマホが相互通信できる自宅LAN |

デフォルトの接続先は次のとおりです。番号は **GPIO番号と基板の物理ピン番号が異なります**。

| 接続 | Pico WのGPIO | 物理ピン |
| --- | --- | --- |
| 送信回路の入力 | GP17 | 22 |
| 受信モジュールのデジタル出力 | GP26 | 31 |
| 対応する3.3 V受信モジュールの電源 | 3V3(OUT) | 36 |
| 共通GND | GND | 例: 38 |

赤外線LEDをGPIOから大電流で直接駆動せず、電流制限抵抗とトランジスター等を使用してください。送信回路の入力にはプルダウン抵抗を設け、起動中も消灯する回路にします。LEDの電流、抵抗値、トランジスターの端子配列は使用部品の仕様に合わせてください。**Pico Wの入力へ5 Vを入れないでください。** 既存のADC用センサーがこのデジタル受信方式に合うかは、センサーの型番/回路を確認する必要があります。

受信部がない場合は `IR_RECEIVE_PIN = None` にできます。その場合は別途取得した正しいプリセットが必要です。受信部なし・信号なしの状態では、エアコンの操作コードは自動生成できません。

## 初期設定（Windowsの例）

### 1. コードとファームウェアを準備

```powershell
git clone https://github.com/YutoKz/PicoW-InfraredRemoteController.git
cd PicoW-InfraredRemoteController
```

この変更がPR段階で、まだmainへマージされていない場合は、続けて `git switch feat/ac-remote-control` を実行してください。

[公式Pico Wファームウェア](https://micropython.org/download/RPI_PICO_W/)を用意します。既存データがある場合は先にバックアップしてください。Pico WをBOOTSELを押しながらUSB接続し、表示されるドライブへUF2をコピーします。通常のPico用ではなく、**Pico W用**を使います。

```powershell
py -m pip install mpremote
Copy-Item config.example.py config.py
py -c "import secrets; print(secrets.token_hex(32))"
```

最後のコマンドで生成したキーと、Wi-Fi情報を `config.py` に設定します。

```python
WIFI_SSID = "自宅の2.4GHz-WiFi名"
WIFI_PASSWORD = "WiFiのパスワード"
API_TOKEN = "生成した64文字のキー"
```

残りの設定項目は `config.example.py` のまま残します。`config.py` と学習データの `codes/` はGitの管理対象外です。パスワードやキーをREADME・Issue・PRへ貼らないでください。

### 2. Pico Wへ書き込む

Thonnyなど、同じシリアルポートを使っているソフトは閉じてから実行します。

```powershell
py -m mpremote connect list
py tools/deploy.py --port COM5 --reset
py -m mpremote connect COM5 repl
```

`COM5` は実際のポート名に置き換えます。1台だけなら `--port auto` でも構いません。Linux/macOSは `py` を `python3`、ポートを `/dev/ttyACM0` 等に変更します。

`deploy.py` は必要な11ファイルだけをコピーし、設定・import・PIOアセンブルを実機上で確認してから再起動します。`legacy/`、テスト、調査PDFは転送しません。既存の `codes/` も上書きしません。

起動時に以下のようなURLが表示されます。

```text
Open http://192.168.3.50:80 on your LAN/VPN
```

表示を見逃した場合、REPLで `Ctrl-C` を押し、次を実行するとIPを確認できます。その後 `Ctrl-D` で再起動してください。

```python
import network
print(network.WLAN(network.STA_IF).ifconfig()[0])
```

REPLを閉じる操作は `Ctrl-]`。ルーターのDHCP予約でPico WのIPを固定すると、毎回同じURLを使えます。コード側では固定IPを無理に上書きしません。

### 3. リモコンを学習

1. スマホを同じWi-Fiへ接続し、表示されたURLをブラウザで開きます。
2. `API_TOKEN` の値をアクセスキーとして入力します。
3. 「リモコンを学習」を開き、ID `cool_26`、表示名「冷房26℃・風量自動」などを入力します。
4. 元のリモコンを希望のモード・温度・風量・風向にします。
5. 「学習を開始」を押し、約1秒待ってから元のリモコンを受信部へ向けて1回押します。長押ししないでください。押した操作によって希望する**最終設定**の信号が送られるようにします。
6. 保存されたボタンを押し、エアコンが希望した設定になるか現場で確認します。
7. **停止用の信号も別途 `off` として学習・確認**します。

受信モジュールは搬送波を取り除いた信号を出力するため、周波数自体は学習できません。デフォルト38 kHzで動作しない場合は、機種の仕様・実測に合わせて変更します。

プリセット例は「登録名の例」であり、これらの信号は事前に入っていません。

| ID例 | 元リモコンで学習させる最終状態 |
| --- | --- |
| `off` | 停止 |
| `cool_26` | 冷房26℃、風量自動、希望する風向 |
| `heat_22` | 暖房22℃、風量自動、希望する風向 |
| `dry` | 除湿、希望する設定 |
| `fan` | 送風（対応機種のみ） |

電源ボタンがトグル式の場合、同じ信号でON/OFFが逆転する可能性があります。**名前を `off` にしただけで「必ず停止」になるわけではありません。** 同じ信号を2回送った場合や、別設定から送った場合も確認してください。

### USBから学習・再送する場合

ブラウザを使わず、`mpremote ... repl` で `Ctrl-C` を押してから実行することもできます。

```python
import read
read.learn("cool_26", "冷房26℃・風量自動")
# Readyが出たら元リモコンを1回押す
import send
send.send("cool_26")
```

同じIDを意図して置き換える場合は `read.learn(..., overwrite=True)` を使います。終わったら `Ctrl-D` で通常起動します。モジュールをimportするだけでは送信しません。

## 外出先から接続

[VPN接続の手順](docs/remote-access.md)を参照してください。自宅に常時動くLinux端末を置き、TailscaleのサブネットルーターとしてPico Wへの経路を提供する例を記載しています。Pico WのHTTPポートを直接インターネットへ公開しません。

## API

APIはすべて `Authorization: Bearer <API_TOKEN>` が必要です。POSTは `Content-Type: application/json` と正しい `Content-Length` が必要です。自動再試行は行わないでください。通信が切れた場合、送信が既に実行されたかはクライアントから判断できないことがあります。

| メソッド / パス | 内容 / JSONボディ |
| --- | --- |
| `GET /` | 操作画面（キーは含まない） |
| `GET /api/presets` | 登録した操作の一覧 |
| `GET /api/status` | 学習可能か・最後に送信したID。実機の運転状態は `unknown` |
| `POST /api/send` | `{"id":"cool_26"}` |
| `POST /api/learn` | `{"id":"cool_26","label":"冷房26℃","carrier_hz":38000}`。既存IDの暗黙の置換は禁止 |
| `POST /api/delete` | `{"id":"cool_26"}`。学習データだけを削除、赤外線送信なし |

`sent` はPIOによる送信完了を示し、エアコンの受信や動作確認を意味しません。実際の状態フィードバックや室温計測機能はありません。

## 保存形式・バックアップ

学習結果はPico W上の `codes/<id>.json` に保存します。UTF-8のJSONで `version`、`id`、`label`、`carrier_hz`、`pulses_us` を持ちます。`pulses_us` はmark（赤外線ONの区間）から始まり、space、mark…と交互に続くマイクロ秒の整数列で、最後もmarkです。コマンド内の空白を含め、最後の無信号待機は含めません。

PCへのバックアップ例:

```powershell
py -m mpremote connect COM5 fs cp -r :codes .
```

復元例（バックアップした `codes` がPC上にある状態）:

```powershell
py -m mpremote connect COM5 fs cp -r codes :
py -m mpremote connect COM5 reset
```

バックアップ後も通常動作へ戻すには `mpremote ... reset` または電源の入れ直しを行ってください。

## トラブルシューティング

| 症状 | 確認事項 |
| --- | --- |
| `Setup required` | `config.py`、全設定項目、32文字以上のキー、転送した全ファイル |
| Wi-Fi接続できない | 2.4 GHz、SSID/パスワード、電波、ルーター側制限 |
| ブラウザで開けない | LAN内IP、同じLAN/VPN、ゲスト分離、スマホ側のHTTPS強制設定 |
| 学習ボタンがない | `IR_RECEIVE_PIN=None` になっていないか |
| 学習タイムアウト | デジタル復調受信部の型番、電源電圧、ピン配列、GP番号、距離 |
| `Receiver must be idle HIGH` | 出力極性、配線、ノイズ、受信部が復調型か |
| パルスが短い/多すぎる | ノイズ、直射光、近すぎる/遠すぎる、長押し、割り込み遅延 |
| 一部だけ記録される | `CAPTURE_IDLE_MS` が機種の内部フレーム間隔より短くないか（最大500 ms） |
| 送信完了なのに反応しない | 赤外線LEDの向き・駆動電流・極性、搬送波、学習欠落、機種が赤外線式か |
| Wi-Fi復旧後URLが違う | DHCP予約を設定する |

## 開発・互換性

```sh
python -m unittest discover -s tests -v
```

[テスト範囲と実機受け入れ手順](docs/validation.md)を参照してください。

旧版はKOIZUMI照明をMQTTで操作する実験コードでした。旧 `main.py`、`send.py`、`read.py`、`wifi.py` は `legacy/` に保存しています。**新しい `main.py` はHTTP/VPN方式で、MQTTトピック `koizumi` には購読しません。** 旧版の信号データや調査PDFは変更していません。`legacy/` は当時の参考用で、未定義変数や設定未入力なども元のまま残しています。

参考:

- [MicroPython PIO](https://docs.micropython.org/en/v1.26.0/library/rp2.html)
- [MicroPython interrupt handlers](https://docs.micropython.org/en/v1.26.0/reference/isr_rules.html)
- [mpremote](https://docs.micropython.org/en/v1.26.0/reference/mpremote.html)
- [Raspberry Pi Pico公式資料](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [IRremoteESP8266: エアコンの赤外線に関するFAQ](https://github.com/crankyoldgit/IRremoteESP8266/wiki/Frequently-Asked-Questions)
- 旧照明実装の参考: https://www.ekit-tech.com/?p=2535
