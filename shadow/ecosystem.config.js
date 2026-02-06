module.exports = {
  apps: [{
    name: 'shadow-gateway',
    cwd: './gateway',
    script: 'src/index.js',

    // Logs
    output: '../logs/gateway-out.log',
    error: '../logs/gateway-error.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',

    // Reiniciar se crashar
    autorestart: true,
    max_restarts: 10,
    restart_delay: 5000,

    // Ambiente
    env: {
      NODE_ENV: 'production'
    }
  }]
}
