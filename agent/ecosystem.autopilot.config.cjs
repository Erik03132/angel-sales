module.exports = {
  apps: [
    {
      name: "a2a-autopilot",
      cwd: "/Users/igorvasin/freelance-2026/projects/ai-eggs",
      script: "agent/autopilot.py",
      interpreter: "/Users/igorvasin/freelance-2026/projects/ai-eggs/.venv/bin/python3",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        A2A_GOVERNANCE_ENFORCE: "0",
      },
    },
  ],
};
