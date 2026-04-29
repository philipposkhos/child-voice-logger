# 童聲記錄 (Child Voice Logger)

建立一個簡單的語音記錄庫記錄兒童的各種聲音。
單界面直接上傳和播放，方便上傳，方便聽。
直接識別檔案名，方便之後再整理。

> **注意：** 說明會直接作為檔名的一部分，因此需遵守系統檔名規則——不支持空格和特殊符號。如果是需要空格的語言（如英文），建議使用大寫格式（例：`HappyMemory`）。

## 本機部署

1. 確認已安裝 Python 3.11+ 和 ffmpeg

2. 安裝依賴

```bash
cd child-voice-logger
pip install -r requirements.txt
```

3. 啟動服務

```bash
APP_USER=你的帳號 APP_PASS=你的密碼 uvicorn app.main:app --host 0.0.0.0 --port 9006
```

4. 開啟瀏覽器進入 http://localhost:9006，輸入帳號密碼即可使用

開發模式加上 `--reload`：

```bash
APP_USER=admin APP_PASS=admin uvicorn app.main:app --reload --port 9006
```

## Docker 部署

1. 修改 docker-compose.yaml 中的帳號密碼：

```yaml
version: "3.8"

services:
  child-voice-logger:
    image: ghcr.io/philipposkhos/child-voice-logger:latest
    ports:
      - "9006:9006"
    volumes:
      - ./app/uploads:/app/uploads
    environment:
      - APP_USER=你的帳號
      - APP_PASS=你的密碼
```

2. 啟動服務

```bash
docker compose up -d
```

3. 開啟瀏覽器進入 http://localhost:9006，輸入帳號密碼即可使用

自行建置：

```bash
docker compose up --build
```

錄音檔會儲存在本地 `./app/uploads` 目錄，容器重啟不會遺失。

## License

MIT
