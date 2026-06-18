import sqlite3
import pandas as pd
import os

DB_PATH = "data/sample.db"

def create_database():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript("""
        DROP TABLE IF EXISTS reviews;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS products;

        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            state TEXT NOT NULL,
            signup_date TEXT NOT NULL
        );

        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        );

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE reviews (
            review_id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            review_date TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
    """)

    customers = pd.DataFrame({
        "customer_id": range(1, 51),
        "name": [f"Customer {i}" for i in range(1, 51)],
        "email": [f"customer{i}@example.com" for i in range(1, 51)],
        "state": ["TX", "CA", "NY", "FL", "WA"] * 10,
        "signup_date": pd.date_range("2023-01-01", periods=50, freq="W").astype(str).tolist()
    })

    products = pd.DataFrame({
        "product_id": range(1, 21),
        "name": [f"Product {i}" for i in range(1, 21)],
        "category": ["Electronics", "Clothing", "Home", "Sports", "Books"] * 4,
        "price": [19.99, 49.99, 99.99, 149.99, 199.99] * 4
    })

    import random
    random.seed(42)
    orders = pd.DataFrame({
        "order_id": range(1, 201),
        "customer_id": [random.randint(1, 50) for _ in range(200)],
        "product_id": [random.randint(1, 20) for _ in range(200)],
        "amount": [round(random.uniform(10, 500), 2) for _ in range(200)],
        "order_date": pd.date_range("2024-01-01", periods=200, freq="D").astype(str).tolist(),
        "status": random.choices(["completed", "pending", "cancelled", "refunded"], k=200)
    })

    reviews = pd.DataFrame({
        "review_id": range(1, 101),
        "product_id": [random.randint(1, 20) for _ in range(100)],
        "customer_id": [random.randint(1, 50) for _ in range(100)],
        "rating": [random.randint(1, 5) for _ in range(100)],
        "comment": [f"Review comment {i}" for i in range(1, 101)],
        "review_date": pd.date_range("2024-01-01", periods=100, freq="2D").astype(str).tolist()
    })

    customers.to_sql("customers", conn, if_exists="replace", index=False)
    products.to_sql("products", conn, if_exists="replace", index=False)
    orders.to_sql("orders", conn, if_exists="replace", index=False)
    reviews.to_sql("reviews", conn, if_exists="replace", index=False)

    conn.commit()
    conn.close()
    print(f"Database created at {DB_PATH}")
    print(f"  customers: {len(customers)} rows")
    print(f"  products:  {len(products)} rows")
    print(f"  orders:    {len(orders)} rows")
    print(f"  reviews:   {len(reviews)} rows")

if __name__ == "__main__":
    create_database()
