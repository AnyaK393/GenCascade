<?php
require __DIR__ . '/../config.php';
require __DIR__ . '/../lib/db.php';
require __DIR__ . '/../lib/auth.php';

const REMEMBER_DAYS = 30;
$error = '';
$email = $_COOKIE['uploader_email'] ?? '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    check_csrf();
    $email = trim($_POST['email'] ?? '');
    try {
        $staff = find_staff($email);
        if ($staff && password_verify($_POST['password'] ?? '', $staff['password_hash'])) {
            session_regenerate_id(true);
            $_SESSION['email'] = $staff['email'];
            $_SESSION['name'] = $staff['name'];
            $expires = isset($_POST['remember']) ? time() + REMEMBER_DAYS * 86400 : time() - 3600;
            setcookie('uploader_email', $staff['email'], ['expires' => $expires, 'httponly' => true, 'samesite' => 'Lax']);
            header('Location: index.php');
            exit;
        }
        $error = 'Wrong e-mail or password.';
    } catch (PDOException $ex) {
        error_log($ex->getMessage());
        $error = 'The database is not reachable. Try again shortly.';
    }
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notes uploader login</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
<main class="narrow">
  <h1>Notes uploader</h1>
  <?php if ($error): ?><p class="notice warn"><?= e($error) ?></p><?php endif; ?>
  <form method="post" class="stack">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <label>E-mail <input type="email" name="email" value="<?= e($email) ?>" autocomplete="username" required></label>
    <label>Password <input type="password" name="password" autocomplete="current-password" required></label>
    <label class="inline"><input type="checkbox" name="remember" <?= $email ? 'checked' : '' ?>> Remember my e-mail</label>
    <button>Log in</button>
  </form>
</main>
</body>
</html>
