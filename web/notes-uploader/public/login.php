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
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 40 40%27%3E%3Cpath d=%27M20 2 35 7.500v11.700c0 9.200-6.100 16.300-15 18.800C11.100 35.500 5 28.400 5 19.200V7.500z%27 fill=%27%23105e58%27/%3E%3Cpath d=%27M12 13h16v4H12z%27 fill=%27%23a7dfd6%27/%3E%3Cpath d=%27M15 19.500h10v4H15z%27 fill=%27%23f7cf6e%27/%3E%3Cpath d=%27M18 26h4v4h-4z%27 fill=%27%23e8674a%27/%3E%3C/svg%3E">
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
