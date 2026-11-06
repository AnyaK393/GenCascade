-- Run once on Fedora as the MySQL root user:  sudo mysql < web/sql/schema.sql
-- Spring Boot creates staff_user, course and exam itself (ddl-auto=update).
-- Change the password below to match MYSQL_PASSWORD in .env.
CREATE DATABASE IF NOT EXISTS cascadeshield_web;
CREATE USER IF NOT EXISTS 'csweb'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON cascadeshield_web.* TO 'csweb'@'localhost';
FLUSH PRIVILEGES;

USE cascadeshield_web;

CREATE TABLE IF NOT EXISTS status_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  level INT NULL,
  banner VARCHAR(200) NOT NULL,
  exam_active BOOLEAN NOT NULL,
  changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS note_upload (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  course VARCHAR(16) NOT NULL,
  topic VARCHAR(40) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  uploaded_by VARCHAR(120) NOT NULL,
  status VARCHAR(16) NOT NULL,          -- indexed | pending | failed
  chunks INT NULL,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
