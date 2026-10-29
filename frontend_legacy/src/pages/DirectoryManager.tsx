import React, { useState } from "react";
import "./DirectoryManager.css";

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  access: string;
  status: "Active" | "Inactive";
  lastActive: string;
}

export const DirectoryManager: React.FC = () => {
  const [search, setSearch] = useState("");

  const users: User[] = [
    {
      id: "USR-001",
      name: "Administrator",
      email: "admin@eyespy.local",
      role: "Administrator",
      access: "Full Access",
      status: "Active",
      lastActive: "Just now",
    },
    {
      id: "USR-002",
      name: "Security Operator",
      email: "operator@eyespy.local",
      role: "Operator",
      access: "Operations",
      status: "Active",
      lastActive: "2 min ago",
    },
    {
      id: "USR-003",
      name: "Incident Responder",
      email: "responder@eyespy.local",
      role: "Responder",
      access: "Operations",
      status: "Active",
      lastActive: "15 min ago",
    },
  ];

  const filteredUsers = users.filter(
    (user) =>
      user.name.toLowerCase().includes(search.toLowerCase()) ||
      user.email.toLowerCase().includes(search.toLowerCase()) ||
      user.role.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="directory-page">
      <header className="directory-header">
        <div>
          <div className="directory-breadcrumb">
            EYESPY <span>/</span> ACCESS CONTROL
          </div>

          <h1>Directory Management</h1>

          <p>
            Manage users, roles, permissions, and access to EyeSpy.
          </p>
        </div>

        <button className="directory-add-button">
          <span>+</span>
          Add User
        </button>
      </header>

      {/* STATISTICS */}
      <div className="directory-stats">
        <div className="directory-stat">
          <span className="stat-icon">◉</span>
          <div>
            <span>TOTAL USERS</span>
            <strong>24</strong>
          </div>
        </div>

        <div className="directory-stat">
          <span className="stat-icon green-icon">●</span>
          <div>
            <span>ACTIVE</span>
            <strong>21</strong>
          </div>
        </div>

        <div className="directory-stat">
          <span className="stat-icon">◈</span>
          <div>
            <span>ADMINS</span>
            <strong>3</strong>
          </div>
        </div>

        <div className="directory-stat">
          <span className="stat-icon">⌁</span>
          <div>
            <span>ONLINE NOW</span>
            <strong>7</strong>
          </div>
        </div>
      </div>

      {/* USER TABLE */}
      <section className="directory-card">
        <div className="directory-toolbar">
          <div>
            <h2>Users &amp; Access</h2>
            <p>Manage registered EyeSpy users.</p>
          </div>

          <div className="directory-actions">
            <div className="directory-search">
              <span>⌕</span>

              <input
                type="text"
                placeholder="Search users..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <button className="filter-button">☷ Filter</button>
          </div>
        </div>

        <div className="directory-table">
          <div className="directory-table-header">
            <span>USER</span>
            <span>ROLE</span>
            <span>ACCESS LEVEL</span>
            <span>STATUS</span>
            <span>LAST ACTIVE</span>
            <span />
          </div>

          {filteredUsers.map((user) => (
            <div className="directory-table-row" key={user.id}>
              <div className="user-cell">
                <div className="user-avatar">
                  {user.name.charAt(0)}
                </div>

                <div>
                  <strong>{user.name}</strong>
                  <span>{user.email}</span>
                </div>
              </div>

              <span className="role-text">{user.role}</span>

              <span className="access-badge">{user.access}</span>

              <span
                className={
                  user.status === "Active"
                    ? "user-status active"
                    : "user-status inactive"
                }
              >
                <i />
                {user.status}
              </span>

              <span className="last-active">{user.lastActive}</span>

              <button className="user-menu">•••</button>
            </div>
          ))}
        </div>

        {filteredUsers.length === 0 && (
          <div className="empty-users">
            <span>⌕</span>
            <strong>No users found</strong>
            <p>Try changing your search.</p>
          </div>
        )}

        <div className="directory-footer">
          <span>
            Showing <strong>{filteredUsers.length}</strong> of{" "}
            <strong>{users.length}</strong> users
          </span>

          <div className="pagination">
            <button disabled>‹</button>
            <button className="current">1</button>
            <button>2</button>
            <button>3</button>
            <button>›</button>
          </div>
        </div>
      </section>

      {/* ROLES */}
      <section className="roles-section">
        <div className="roles-heading">
          <div>
            <h2>Roles &amp; Permissions</h2>
            <p>Define what each role can access within EyeSpy.</p>
          </div>

          <button className="secondary-directory-button">
            Manage Roles
          </button>
        </div>

        <div className="roles-grid">
          <div className="role-card">
            <span className="role-card-icon">◆</span>
            <h3>Administrator</h3>
            <p>Full system and configuration access.</p>
            <span className="role-users">3 users</span>
          </div>

          <div className="role-card">
            <span className="role-card-icon">◉</span>
            <h3>Operator</h3>
            <p>Live monitoring and incident management.</p>
            <span className="role-users">8 users</span>
          </div>

          <div className="role-card">
            <span className="role-card-icon">◇</span>
            <h3>Responder</h3>
            <p>Incident response and physical security enforcement.</p>
            <span className="role-users">10 users</span>
          </div>
        </div>
      </section>
    </div>
  );
};
