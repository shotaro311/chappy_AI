# Wake Word × GPT × Googleカレンダー アシスタント

```
Wake Word → ChatGPT Realtime → Googleカレンダー → 音声通知
```

## セットアップ

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `.env` を `.env.example` から作成し、APIキーと `APP_ENV` を設定
4. `make run`

## 構成
- `src/main.py`: 共有エントリーポイント
- `src/wakeword/`: Porcupine を使った監視
- `src/realtime/`: ChatGPT Realtime API クライアント
- `src/calendar/`: Googleカレンダー連携
- `src/audio/`: マイク入力とスピーカー出力
- `src/vad/`: 無音検知とセッション制御
- `config/`: base と環境別設定

## 開発フロー
- `make lint` / `make format` / `make test`
- `PYTHONPATH=src python -m src.main --config config/pc.dev.yaml`
- Raspberry Pi へは `make sync-config`
