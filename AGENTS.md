# Repository Guidelines

## プロジェクト構成とモジュール配置
本リポジトリは `docs/要件定義.md` に要件がまとまっており、プロダクトコードは `src/` 以下に Python モジュールとしてまとめる前提です。`src/wakeword`, `src/audio`, `src/realtime`, `src/calendar`, `src/vad`, `src/config`, `src/util` を分割し、共有エントリーポイントは `src/main.py` に集約します。設定は `config/base.yaml` を共通にし、`config/pc.dev.yaml` と `config/rpi.prod.yaml` で環境差分を吸収してください。認証情報は `.env` に集約し、サンプルを `.env.example` に維持します。音声サンプルや Wake Word モデルは `assets/audio` `assets/models` 配下に置き、`git lfs track assets/**/*` でサイズ制限を回避してください。

## ビルド・テスト・開発コマンド
まず `python -m venv .venv && source .venv/bin/activate` で仮想環境を用意し、`pip install -r requirements.txt` を実行します。アプリは `python -m src.main --config config/pc.dev.yaml` でローカル実行し、`PYTHONPATH=src` を export しておくと補完が安定します。ユーティリティスクリプトは `make lint`, `make test`, `make sync-config` のように Makefile へまとめ、Raspberry Pi 同期は `rsync -av src pi:/opt/chappy_ai/src` を推奨します。CI は GitHub Actions で `make lint test` を直列実行し、生成された `coverage.xml` を `codecov` にアップロードします。

## コーディングスタイルと命名
Python 3.11 を前提とし、型ヒントは `typing.Annotated` まで活用します。静的解析は `ruff check`、整形は `ruff format` または `black`、循環参照を避けるため各モジュールは API 境界を `__all__` で明示してください。クラス名は UpperCamel、モジュール名は snake_case。ログは `logging_utils.get_logger(__name__)` から取得し、Wake Word や API など機微情報は log redaction を実施します。

## テスト指針
`tests/` をプロダクションモジュールに対応するミラー構成にし、`tests/realtime/test_openai_client.py` のように命名します。`pytest -m "not slow"` をデフォルトとし、音声 I/O を伴う遅いテストは `@pytest.mark.slow` を付けて Raspberry Pi 上のみで実行します。日付計算は `freezegun` で固定し、Google API 呼び出しは `responses` で完全にモックします。最低 80% line coverage を維持し、CI 失敗時は必ず修正コミットを追加します。

## コミットと Pull Request
`git log` は日本語の簡潔な記述（例: "Wake Word 監視ループを整理"）で統一されているため、50 文字以内の要約 + 詳細本文の Conventional Comments を推奨します。PR では目的、主要変更点、テスト結果、関連 Issue、音声確認があればスクリーンショットやログを添付してください。設定値や秘密鍵を扱った場合は復旧手順も明記し、レビュー前に `make lint test` を必ず通過させます。

## セキュリティと設定
`OPENAI_API_KEY`、`GOOGLE_REFRESH_TOKEN` などは `direnv` や 1Password CLI で注入し、リポジトリには決して平文で残さないでください。Porcupine AccessKey やカレンダーの Service Account JSON は `config/secure/` の暗号化ストア（例: `age`）に置き、復号手順を RUNBOOK.md に追記します。マイク・スピーカーのデバイス ID は `aplay -l` や `arecord -l` の出力を貼り付け、Raspberry Pi では `systemd --user` サービスとして自動起動させることでセッションタイムアウト時のリカバリーを簡略化します。
