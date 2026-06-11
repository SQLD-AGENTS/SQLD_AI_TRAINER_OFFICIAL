import { Link, useMatch, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import Avatar from '../ui/Avatar';

export default function TopBar() {
  const { user, isGuest, logout } = useAuth();
  const isUser = !!user && !isGuest;
  const navigate = useNavigate();

  const questionsActive = useMatch('/questions/*');
  const dashboardActive = useMatch('/dashboard');
  const recommendActive = useMatch('/recommend');

  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <div className="glyph">S</div>
        <span>SQLD<span style={{ color: 'var(--accent)', marginLeft: 4 }}>AI</span></span>
      </Link>

      <nav>
        <Link to="/questions" className={questionsActive ? 'is-active' : ''}>문제</Link>
        {isUser && (
          <Link to="/dashboard" className={dashboardActive ? 'is-active' : ''}>대시보드</Link>
        )}
        {isUser && (
          <Link to="/recommend" className={recommendActive ? 'is-active' : ''}>AI 추천</Link>
        )}
      </nav>

      <div className="right">
        {!user ? (
          <>
            <Link to="/login"><button className="btn btn-sm">로그인</button></Link>
            <Link to="/register"><button className="btn btn-primary btn-sm">회원가입</button></Link>
          </>
        ) : isGuest ? (
          <>
            <span className="t-caption" style={{ color: 'var(--text-2)' }}>게스트</span>
            <Link to="/login"><button className="btn btn-primary btn-sm">로그인</button></Link>
          </>
        ) : (
          <>
            <button
              className="btn-icon"
              onClick={() => navigate('/profile')}
              title="프로필"
              style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', padding: '4px 8px', borderRadius: 8 }}
            >
              <Avatar username={user.username} size={32} fontSize={13} />
              <span className="t-caption" style={{ color: 'var(--text-2)' }}>{user.username}</span>
            </button>
            <button className="btn btn-outline btn-sm" onClick={logout}>로그아웃</button>
          </>
        )}
      </div>
    </header>
  );
}
