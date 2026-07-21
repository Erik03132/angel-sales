module.exports = {
  apps: [
    {
      name: "a2a-dispatcher",
      cwd: "/Users/igorvasin/freelance-2026/projects/ai-eggs",
      script: "agent/a2a_dispatcher.py",
      interpreter: "/Users/igorvasin/freelance-2026/projects/ai-eggs/.venv/bin/python3",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        A2A_GOVERNANCE_ENFORCE: "0",
        A2A_TRUSTED_SENDERS: "smoke,test,external,autopilot",
      },
    },
  ],
};
