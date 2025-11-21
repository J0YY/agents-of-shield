const express = require('express');
const path = require('path');
const fs = require('fs');
const sqlite3 = require('sqlite3').verbose();

const app = express();
const PORT = process.env.PORT || 3000;
const DB_PATH = path.join(__dirname, 'users.db');
const LOG_PATH = path.join(__dirname, 'attack_log.json');

// Basic SQLite setup (intentionally minimal and unsafe)
const db = new sqlite3.Database(DB_PATH);
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    password TEXT,
    credit_card_last4 TEXT
  )`);

  db.get('SELECT COUNT(*) as count FROM users', (err, row) => {
    if (err) {
      console.error('Failed to count users', err);
      return;
    }

    if (!row.count) {
      db.run(`INSERT INTO users (name, email, phone, password, credit_card_last4)
        VALUES ('Sofia Alvarez', 'sofia@example.com', '555-123-4567', 'poodlelover', '4242')`);
    }
  });
});

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Intentional all-request logging for defenders to watch
app.use((req, res, next) => {
  const logEntry = {
    timestamp: new Date().toISOString(),
    ip: req.ip,
    method: req.method,
    endpoint: req.originalUrl,
    query: req.query,
    body: req.body
  };

  fs.appendFile(LOG_PATH, JSON.stringify(logEntry) + '\n', (err) => {
    if (err) {
      console.error('Unable to write attack log', err);
    }
  });

  next();
});

app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req, res) => {
  res.render('index');
});

app.get('/signup', (req, res) => {
  res.render('signup');
});

app.post('/signup', (req, res) => {
  const { name = '', email = '', phone = '', password = '', cardNumber = '' } = req.body;
  const last4 = cardNumber.slice(-4) || '0000';

  // Intentionally vulnerable SQL string concatenation
  const unsafeInsert = `INSERT INTO users (name, email, phone, password, credit_card_last4)
    VALUES ('${name}', '${email}', '${phone}', '${password}', '${last4}')`;

  db.run(unsafeInsert, (err) => {
    if (err) {
      return res.status(500).send(`<h2>Signup failed</h2><pre>${err.message}</pre>`);
    }

    res.send('<h2>Account created!</h2><p><a href="/login">Login now</a></p>');
  });
});

app.get('/login', (req, res) => {
  res.render('login');
});

app.post('/login', (req, res) => {
  const { email = '', password = '' } = req.body;
  const unsafeQuery = `SELECT * FROM users WHERE email = '${email}' AND password = '${password}' LIMIT 1`;

  db.get(unsafeQuery, (err, user) => {
    if (err) {
      return res.status(500).send(`<h2>Login error</h2><pre>${err.message}</pre>`);
    }

    if (!user) {
      return res.status(401).send('<h2>Invalid credentials</h2><p><a href="/login">Try again</a></p>');
    }

    res.redirect(`/dashboard?user=${encodeURIComponent(email)}`);
  });
});

app.get('/dashboard', (req, res) => {
  const email = req.query.user || '';
  let query = 'SELECT * FROM users ORDER BY id DESC LIMIT 1';

  if (email) {
    query = `SELECT * FROM users WHERE email = '${email}' LIMIT 1`;
  }

  db.get(query, (err, user) => {
    if (err || !user) {
      return res.status(404).send('<h2>User not found</h2>');
    }

    res.render('dashboard', { user });
  });
});

app.get('/admin', (req, res) => {
  db.all('SELECT * FROM users', (err, users) => {
    if (err) {
      return res.status(500).send('Unable to load users');
    }

    res.render('admin', {
      users,
      dbPath: DB_PATH
    });
  });
});

app.get('/download-db', (req, res) => {
  const file = req.query.file || 'users.db';
  const filePath = path.resolve(__dirname, file);
  res.download(filePath, (err) => {
    if (err) {
      res.status(404).send('File not found');
    }
  });
});

app.get('/debug', (req, res) => {
  db.all('SELECT email, password FROM users', (err, rows) => {
    res.json({
      env: process.env.NODE_ENV || 'development',
      sampleUsers: rows || [],
      secrets: {
        apiKey: 'internal-dev-key-999',
        stripe: 'sk_live_fake_0001'
      },
      headers: req.headers
    });
  });
});

app.get('/env', (req, res) => {
  res.json(process.env);
});

app.get('/source', (req, res) => {
  const file = req.query.file || 'app.js';
  const targetPath = path.join(__dirname, file);

  fs.readFile(targetPath, 'utf8', (err, data) => {
    if (err) {
      return res.status(404).send('Unable to read source file');
    }

    res.type('text/plain').send(data);
  });
});

// Honey-pot style decoy endpoints
app.get('/admin-v2', (req, res) => {
  res.json({
    status: 'ok',
    featureFlag: 'admin_v2_preview',
    adminToken: 'fake-token-use-me',
    notes: 'Legacy admin route scheduled for removal'
  });
});

app.get('/backup-db', (req, res) => {
  res.json({
    status: 'queued',
    backupLocation: 's3://pet-grooming-prod/backups/users-2024-10-01.sql',
    integrity: 'pending'
  });
});

app.get('/config-prod', (req, res) => {
  res.json({
    featureFlags: ['beta-dashboard', 'express-checkout'],
    paymentGateway: 'https://payments.internal/petgroom',
    webhookSecret: 'whsec_fake_982734',
    nodeVersion: process.version
  });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Pet Grooming by Sofia listening on port ${PORT}`);
  });
}

module.exports = app;
