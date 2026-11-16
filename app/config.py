import os

DATABASE_URL = os.getenv("SHOPSPHERE_DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/shopsphere_pro")
SECRET_KEY = os.getenv("SHOPSPHERE_SECRET_KEY", "development-secret-change-before-deploy-2026")
