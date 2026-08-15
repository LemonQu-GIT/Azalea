中文版 / [中国語版はこちら](./README.md)

# Azalea Project

> キヴォトスの生徒たちのためのデスクトップペット

---

## 機能

### 会話とAI機能

- **大規模言語モデル連携**：OpenAI API 互換フォーマットに対応
- **Tool Calling**：使用可能な Tools は以下の通り
  - `get_windows_list` — 現在表示されている全ウィンドウの一覧を取得
  - `keyboard_input` — キーボード入力をシミュレート
  - `cmd_run` — システムコマンドを実行（安全性は限定的）
- **会話頻度の自動調整**：ユーザーが長時間反応しない場合、思考間隔を自動的に延長
- **長期記憶**：会話コンテキストを永続化して保存し、意味検索によるメモリ参照に対応

### 音声合成

詳細は https://github.com/High-Logic/Genie-TTS を参照してください

Genie-TTS を使用すると、GPT-SoVITS 互換モデルを ONNX モデルに変換できます

GPT-SoVITS Model by [**@SLNeil**](https://space.bilibili.com/523537077)

日本語の音声を生成したい場合は、設定で TTS の言語を `jp` に設定してください

### API インターフェース

- FastAPI による HTTP + WebSocket インターフェースを提供
- API 経由でモデルの位置・回転・拡大縮小・アニメーション再生を制御可能
- `local` / `global` の2種類の回転座標系に対応

---

## 動作環境

- Python **≥ 3.12**
- Windows および Linux に対応（Linux は X11 を推奨。Wayland ではウィンドウ操作系の機能が一部制限されますが、その場合も安全に動作を継続します）
- Ollama または OpenAI 互換の API
- （任意）Genie-TTS ローカル音声合成 API
- （任意）Embedding ローカル単語ベクトル API

---

## クイックスタート

### 起動・デプロイスクリプトを使う

```bash
python run_project.py
```

### 手動デプロイ

#### 1. プロジェクトをクローン

```bash
git clone https://github.com/LemonQu-GIT/Azalea.git
cd Azalea
```

#### 2. 依存関係をインストール (uv)

* TTS・Embedding などの API をすべてクラウド上で使う場合：

```bash
uv sync
```

* TTS・Embedding API を使わない、あるいはこれらをローカルで動かす場合

  本プロジェクトは LLM API 自体のローカル実行は提供していません。Ollama、OpenAI などのモデルプロバイダーを別途ご利用ください

```bash
uv sync --extra local
```

#### 3. 設定ファイル

サンプル設定ファイルをコピーし、必要に応じて編集します：

Windows の場合：

```bash
copy configs\config.example.json configs\config.json
```

Linux の場合：

```bash
cp configs/config.example.json configs/config.json
```

`configs/config.json` を編集し、少なくとも **LLM 設定**（endpoint、api_key、model）を入力してください

UI の表示言語は、`configs/config.json` のトップレベルにある `"language"` キー（`"zh"` / `"ja"`）で切り替えられます。環境変数 `AZALEA_LANG` を設定するとこちらが優先されます

#### 4. アプリを起動

メインプログラム：

```bash
python main.py
```

Embedding API を起動する場合：

```bash
python embedding_api.py
```

TTS API を起動する場合：

```bash
python tts_api.py
```

起動後：

- デスクトップにペットのウィンドウが表示されます
- システムトレイに Azalea のアイコンが表示され、右クリックで設定や会話を開けます
- デフォルトでは API サービスは `http://127.0.0.1:8001` で動作します

---

## 使い方

### 基本操作

| 操作                                 | 説明                                             |
| ------------------------------------ | ------------------------------------------------ |
| **左クリックでドラッグ**             | ペットを移動させ、離すと物理法則に従って投げ出される |
| **頭部あたりで右クリック長押しスライド** | 頭を撫でる                                        |
| **ペットを右クリック**               | 会話画面を開く                                    |
| **トレイアイコンを右クリック → 設定** | 設定画面を開く（LLM / TTS / テーマなど）           |
| **トレイアイコンを右クリック → 終了** | アプリを終了する                                  |

## セキュリティに関する注意

- `cmd_run` ツールには危険なコマンドのブラックリスト（shutdown/rm/reg など）が組み込まれていますが、プロンプトインジェクション攻撃には十分ご注意ください
- 不要なシステム権限を付与せず、通常のユーザー権限で実行することを推奨します

### TODO

[TODO.md](./TODO.md) を参照してください

---

## ライセンス

本プロジェクトは学習・交流目的のみで使用してください。プロジェクト内の3Dモデル・テクスチャなどの素材の著作権は、元の作者に帰属します。
