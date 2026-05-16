DROP TABLE IF EXISTS Account CASCADE;
DROP TABLE IF EXISTS Savings CASCADE;
DROP TABLE IF EXISTS Checking CASCADE;

CREATE TABLE Account (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    CustomerID INT NOT NULL,
    UNIQUE (CustomerID)
);

CREATE TABLE Savings (
    CustomerID INT PRIMARY KEY,
    Balance float NOT NULL,
    CONSTRAINT fk_customer
        FOREIGN KEY(CustomerID)
        REFERENCES Account(CustomerID)
);

CREATE TABLE Checking (
    CustomerID INT PRIMARY KEY,
    Balance float NOT NULL,
    CONSTRAINT fk_customer
        FOREIGN KEY(CustomerID)
        REFERENCES Account(CustomerID)
);
