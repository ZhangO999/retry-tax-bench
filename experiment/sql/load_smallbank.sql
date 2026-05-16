-- Reference loader shape for psql/manual inspection.
-- The harness uses parameterized Python loading so account_count and balances
-- come from config/experiment_matrix.json.
INSERT INTO Account(name, CustomerID)
SELECT 'name' || i, i
FROM generate_series(1, 18000) AS i;

INSERT INTO Savings(CustomerID, Balance)
SELECT i, 100000
FROM generate_series(1, 18000) AS i;

INSERT INTO Checking(CustomerID, Balance)
SELECT i, 100000
FROM generate_series(1, 18000) AS i;
