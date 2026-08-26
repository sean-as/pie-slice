import { useEffect } from "react";
import { Routes, Route, Link, useNavigate, useLocation } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { SignupPage } from "./pages/SignupPage";
import { LoginPage } from "./pages/LoginPage";
import { GroupPage } from "./pages/GroupPage";
import { useCurrentUser } from "./hooks/useCurrentUser";
import { expenseService } from "./services";
import "./App.css";

export default function App() {
  const { user, refresh } = useCurrentUser();
  const navigate = useNavigate();
  const location = useLocation();

  // The header's session state is a separate hook instance from whatever
  // page just logged in/out, so re-check on every navigation rather than
  // only on mount.
  useEffect(() => {
    refresh();
  }, [location.pathname, refresh]);

  async function handleLogout() {
    await expenseService.logout();
    await refresh();
    navigate("/");
  }

  return (
    <div className="app">
      <header className="site-header">
        <Link to="/" className="brand">
          pie-slice
        </Link>
        {user && (
          <span className="header-user">
            {user.displayName} · <button className="link-button" onClick={handleLogout}>Log out</button>
          </span>
        )}
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/group/:groupId" element={<GroupPage />} />
        </Routes>
      </main>
    </div>
  );
}
