-- Optional: create the MySQL database. The app creates the table automatically on startup.
CREATE DATABASE IF NOT EXISTS trade_ai CHARACTER SET utf8mb4;
USE trade_ai;
CREATE TABLE IF NOT EXISTS analyses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  symbol VARCHAR(30),
  timeframe VARCHAR(10),
  signal_type VARCHAR(10),
  confidence INT,
  price DOUBLE,
  source VARCHAR(20),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  result_json LONGTEXT
) CHARACTER SET utf8mb4;
