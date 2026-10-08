# 勤怠管理 API(マルチテナント)

会社(テナント)ごとにデータが分かれる、出勤・退勤の記録 API。学習用プロジェクト。

**技術**: FastAPI / PostgreSQL 18 (Docker) / SQLAlchemy 2.x / Alembic / JWT + argon2

## 機能

すべて `/tenants/{tenant_id}` 配下。ロールは owner > admin > member。

| 分類 | API | 権限 |
|---|---|---|
| 認証 | `POST /auth/signup` `POST /auth/login` `GET /auth/me` | - |
| 勤怠 | `POST .../attendance/clock-in` `clock-out` | member |
| | `GET .../attendance`(cursor ページング, limit 1–100) | member |
| | `PATCH .../attendance/{id}`(出退勤時刻の修正) | owner |
| メンバー | `GET .../members` | member |
| | `POST .../members`(追加) `DELETE .../members/{user_id}`(論理削除) | admin |
| | `PATCH .../members/{user_id}/role` `GET .../members/{user_id}/attendance` | owner |
| 監査 | `GET .../audit-logs` | admin |

- 所属外・存在しないテナントは 403、テナント内に無い対象は 404、状態の衝突(二重出勤など)は 409
- 勤怠の修正は監査ログに記録される
- プラン上限(free は 5 人まで)、最後の owner は削除・降格不可

## 使い方

```powershell
cp .env.example .env            # 値を編集
docker compose up -d
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## 未対応

- ログアウト / トークン失効 / リフレッシュトークン
- パスワード変更・リセット、メール認証
- テナント作成・削除・プラン変更の API
- 休憩、残業計算、月次集計、CSV 出力
- 時刻は UTC 返却(日本時間変換はクライアント任せ)
- レート制限、本番デプロイ設定、CI
