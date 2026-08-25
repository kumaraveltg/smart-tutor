from app.core.security import verify_password

result = verify_password("admin@123", "$2b$12$tvPnM4HoiGvpw/Uornazf.qXzy7QhAO27x.VevOSQkRFnYSm7tKYK")
print(result)