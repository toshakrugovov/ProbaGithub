# Скрипт для сборки Docker образа с альтернативными методами

Write-Host "Сборка Docker образа для MPTCOURSE..." -ForegroundColor Cyan

# Метод 1: Сборка без BuildKit
Write-Host "`nПопытка 1: Сборка без BuildKit..." -ForegroundColor Yellow
$env:DOCKER_BUILDKIT = "0"
$result = docker-compose build web 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Успешно собрано без BuildKit!" -ForegroundColor Green
    exit 0
}

# Метод 2: Сборка с очисткой кэша
Write-Host "`nПопытка 2: Сборка с очисткой кэша..." -ForegroundColor Yellow
$env:DOCKER_BUILDKIT = "1"
$result = docker-compose build --no-cache web 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Успешно собрано с очисткой кэша!" -ForegroundColor Green
    exit 0
}

# Метод 3: Обычная сборка
Write-Host "`nПопытка 3: Обычная сборка..." -ForegroundColor Yellow
$result = docker-compose build web 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Успешно собрано!" -ForegroundColor Green
    exit 0
}

Write-Host "`nВсе методы не сработали. Проверьте:" -ForegroundColor Red
Write-Host "1. Docker Desktop запущен и работает" -ForegroundColor Yellow
Write-Host "2. Достаточно памяти для Docker (минимум 4GB)" -ForegroundColor Yellow
Write-Host "3. Достаточно места на диске" -ForegroundColor Yellow
Write-Host "4. Попробуйте перезапустить компьютер" -ForegroundColor Yellow


