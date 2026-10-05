def create_tenant_user(client, email: str, tenant_name: str):
    # サインアップ
    signup = client.post("/auth/signup", json={ "tenant_name": tenant_name, "user_name": "string", "email": email, "password": "password" })
    assert signup.status_code == 201
    tenant_id = signup.json()["tenant_id"]
    
    # ログイン
    login = client.post("/auth/login", json={ "email": email, "password": "password" })
    assert login.status_code == 200
    token = login.json()["access_token"]
    
    return tenant_id, token
