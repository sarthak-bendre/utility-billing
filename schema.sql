-- MySQL schema for the Smart Utility Billing and Complaint Management System.
-- The Flask app also creates these tables automatically (db.create_all()),
-- so running this file is optional; it is provided for DBAs / manual setup.

CREATE DATABASE IF NOT EXISTS utility_billing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE utility_billing;

CREATE TABLE IF NOT EXISTS customers (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    account_no       VARCHAR(20)  NOT NULL UNIQUE,
    name             VARCHAR(120) NOT NULL,
    email            VARCHAR(120) NOT NULL UNIQUE,
    phone            VARCHAR(20)  NOT NULL,
    address          VARCHAR(255) NOT NULL,
    connection_type  VARCHAR(20)  NOT NULL DEFAULT 'residential',  -- residential | commercial
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bills (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    bill_no             VARCHAR(30)   NOT NULL UNIQUE,
    customer_id         INT           NOT NULL,
    utility_type        VARCHAR(20)   NOT NULL,                    -- electricity | water
    period_start        DATE          NOT NULL,
    period_end          DATE          NOT NULL,
    previous_reading    DECIMAL(12,2) NOT NULL,
    current_reading     DECIMAL(12,2) NOT NULL,
    units_consumed      DECIMAL(12,2) NOT NULL,
    consumption_charge  DECIMAL(12,2) NOT NULL,
    fixed_charge        DECIMAL(12,2) NOT NULL,
    tax_amount          DECIMAL(12,2) NOT NULL,
    late_fee            DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_amount        DECIMAL(12,2) NOT NULL,
    status              VARCHAR(20)   NOT NULL DEFAULT 'unpaid',   -- unpaid | paid | overdue
    issue_date          DATE          NOT NULL,
    due_date            DATE          NOT NULL,
    paid_date           DATE          NULL,
    INDEX ix_bills_customer (customer_id),
    INDEX ix_bills_status (status),
    CONSTRAINT fk_bills_customer FOREIGN KEY (customer_id)
        REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS complaints (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    ticket_no    VARCHAR(30)  NOT NULL UNIQUE,
    customer_id  INT          NOT NULL,
    category     VARCHAR(20)  NOT NULL,   -- electricity | water | billing | meter | other
    subject      VARCHAR(150) NOT NULL,
    description  TEXT         NOT NULL,
    priority     VARCHAR(20)  NOT NULL DEFAULT 'medium',  -- low | medium | high | critical
    status       VARCHAR(20)  NOT NULL DEFAULT 'open',    -- open | in_progress | resolved | closed
    assigned_to  VARCHAR(120) NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_at  DATETIME     NULL,
    INDEX ix_complaints_customer (customer_id),
    INDEX ix_complaints_status (status),
    CONSTRAINT fk_complaints_customer FOREIGN KEY (customer_id)
        REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS complaint_updates (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    complaint_id  INT          NOT NULL,
    status        VARCHAR(20)  NOT NULL,
    note          TEXT         NULL,
    updated_by    VARCHAR(120) NOT NULL DEFAULT 'system',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_updates_complaint (complaint_id),
    CONSTRAINT fk_updates_complaint FOREIGN KEY (complaint_id)
        REFERENCES complaints(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Example app user:
-- CREATE USER 'utility_user'@'localhost' IDENTIFIED BY 'change_me';
-- GRANT ALL PRIVILEGES ON utility_billing.* TO 'utility_user'@'localhost';
