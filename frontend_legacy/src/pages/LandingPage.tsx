import React from "react";
import { useTheme } from '../context/ThemeContext';
import "./LandingPage.css";

const LandingPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="landing-page">
      {/* ================= NAVBAR ================= */}
      <nav className="landing-navbar">
        <div className="landing-logo">
          <div className="logo-icon">
            <span>◈</span>
          </div>

          <div className="logo-text">
            <span className="logo-eye">Eye</span>
            <span className="logo-spy">Spy</span>
          </div>
        </div>

        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#technology">Technology</a>
          <a href="#about">About</a>
        </div>

        <div className="nav-actions">
          <button
            className="landing-theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <a href="/login" className="nav-login">
            Login
          </a>
        </div>
      </nav>

      {/* ================= HERO ================= */}
      <section className="hero-section">
        <div className="hero-background">
          <div className="hero-glow hero-glow-one" />
          <div className="hero-glow hero-glow-two" />
        </div>

        <div className="hero-content">
          <div className="hero-text">
            <div className="status-badge">
              <span className="status-dot" />
              AI-POWERED SURVEILLANCE
            </div>

            <h1>
              Intelligent
              <br />
              <span>Security.</span>
              <br />
              <strong>Real-Time.</strong>
            </h1>

            <p>
              EyeSpy transforms traditional CCTV monitoring into an
              intelligent security operation with AI-powered detection,
              behavior analysis, and real-time monitoring.
            </p>

            <div className="hero-buttons">
              <a href="/login" className="primary-button">
                Access EyeSpy
                <span>→</span>
              </a>

              <a href="#features" className="secondary-button">
                Explore Features
              </a>
            </div>

            <div className="hero-stats">
              <div>
                <strong>24/7</strong>
                <span>Monitoring</span>
              </div>

              <div>
                <strong>AI</strong>
                <span>Detection</span>
              </div>

              <div>
                <strong>LIVE</strong>
                <span>Analysis</span>
              </div>
            </div>
          </div>

          {/* ================= CAMERA PREVIEW ================= */}
          <div className="camera-wrapper">
            <div className="camera-glow" />

            <div className="camera-card">
              <div className="camera-header">
                <div className="camera-status">
                  <span />
                  LIVE MONITORING
                </div>

                <div className="camera-id">CAM-01</div>
              </div>

              <div className="camera-feed">
                <div className="camera-grid" />

                <div className="camera-placeholder">
                  <div className="camera-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                    >
                      <path
                        d="M15 10l4.5-2.25a1 1 0 011.5.87v6.76a1 1 0 01-1.5.87L15 14"
                        strokeWidth="1.5"
                      />
                      <rect
                        x="3"
                        y="6"
                        width="12"
                        height="12"
                        rx="2"
                        strokeWidth="1.5"
                      />
                    </svg>
                  </div>

                  <span>AI SURVEILLANCE FEED</span>
                </div>

                {/* AI detection box */}
                <div className="detection-box">
                  <span>PERSON</span>
                  <small>98%</small>
                </div>

                <div className="ai-status">
                  <span className="status-dot" />
                  AI ANALYSIS ACTIVE
                </div>

                <div className="camera-time">LIVE</div>
              </div>

              <div className="camera-footer">
                <div>
                  <span>OBJECTS</span>
                  <strong>04</strong>
                </div>

                <div>
                  <span>CONFIDENCE</span>
                  <strong>98.2%</strong>
                </div>

                <div>
                  <span>STATUS</span>
                  <strong className="secure-text">SECURE</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ================= FEATURES ================= */}
      <section id="features" className="features-section">
        <div className="section-heading">
          <span>INTELLIGENT SECURITY</span>

          <h2>
            Beyond Traditional
            <br />
            <strong>CCTV Monitoring</strong>
          </h2>

          <p>
            Turn raw camera footage into meaningful security intelligence.
          </p>
        </div>

        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">◉</div>
            <h3>Live Detection</h3>
            <p>
              Detect people, vehicles, objects, and security events in
              real-time.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">◌</div>
            <h3>Behavior Analysis</h3>
            <p>
              Identify unusual activity and potentially suspicious behavior
              automatically.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">!</div>
            <h3>Smart Alerts</h3>
            <p>
              Receive actionable alerts when important security events are
              detected.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">▦</div>
            <h3>Security Analytics</h3>
            <p>
              Understand incidents through centralized security intelligence
              and analytics.
            </p>
          </div>
        </div>
      </section>

      {/* ================= TECHNOLOGY ================= */}
      <section id="technology" className="technology-section">
        <div className="technology-content">
          <div className="technology-text">
            <span className="section-label">THE TECHNOLOGY</span>

            <h2>
              Intelligence
              <br />
              <strong>At Every Frame.</strong>
            </h2>

            <p>
              EyeSpy combines computer vision, real-time processing,
              behavior analysis, and security analytics into one centralized
              surveillance platform.
            </p>

            <div className="technology-list">
              <div>
                <span>✓</span>
                <p>Real-time computer vision</p>
              </div>

              <div>
                <span>✓</span>
                <p>AI-powered object detection</p>
              </div>

              <div>
                <span>✓</span>
                <p>Behavior and incident analysis</p>
              </div>

              <div>
                <span>✓</span>
                <p>Secure authenticated access</p>
              </div>
            </div>
          </div>

          <div className="technology-panel">
            <div className="tech-panel-header">
              <span>SYSTEM STATUS</span>
              <span className="online">● ONLINE</span>
            </div>

            <div className="tech-metrics">
              <div>
                <strong>AI</strong>
                <span>Computer Vision</span>
              </div>

              <div>
                <strong>LIVE</strong>
                <span>Video Processing</span>
              </div>

              <div>
                <strong>24/7</strong>
                <span>Monitoring</span>
              </div>

              <div>
                <strong>SEC</strong>
                <span>Protected Access</span>
              </div>
            </div>

            <div className="system-line">
              <span />
              SYSTEMS OPERATIONAL
            </div>
          </div>
        </div>
      </section>

      {/* ================= CTA ================= */}
      <section id="about" className="cta-section">
        <div className="cta-card">
          <div className="cta-content">
            <span className="section-label">SECURE YOUR OPERATIONS</span>

            <h2>
              See More.
              <br />
              <strong>Know More.</strong>
            </h2>

            <p>
              EyeSpy transforms conventional CCTV into intelligent security operations — combining real-time monitoring with AI-powered computer vision to detect, analyze, and alert faster than manual review ever could.
            </p>


          </div>
        </div>
      </section>

      {/* ================= FOOTER ================= */}
      <footer className="landing-footer">
        <div className="footer-logo">
          <div className="logo-icon small">
            <span>◈</span>
          </div>

          <span>
            Eye<span>Spy</span>
          </span>
        </div>

        <p>AI-POWERED INTELLIGENT SURVEILLANCE</p>
        <div>
          <h4 className="font-semibold mb-4 text-foreground">Features</h4>
          <ul className="space-y-2 text-muted-foreground">
            <li>Object Detection</li>
            <li>Motion Analysis</li>
            <li>Real-time Tracking</li>
            <li>Pose Estimation</li>
          </ul>
        </div>
        <div>
          <h4 className="font-semibold mb-4 text-foreground">Contact Team</h4>
          <div className="space-y-3 text-muted-foreground">
            <div className="flex items-center space-x-2">
              <span>project@eyespy.local</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>+1 (555) 000-0000</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>Campus Innovation Lab</span>
            </div>
          </div>
        </div>
        <span>© 2026 EyeSpy</span>
      </footer>
    </div>
  );
};

export { LandingPage };