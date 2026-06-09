import { useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Avatar from '../components/ui/Avatar';
import PageLayout from '../components/layout/PageLayout';
import ProfileBasicInfo from '../components/profile/ProfileBasicInfo';
import ProfilePasswordChange from '../components/profile/ProfilePasswordChange';
import ProfileStats from '../components/profile/ProfileStats';
import ProfileDangerZone from '../components/profile/ProfileDangerZone';
import ProfileComingSoon from '../components/profile/ProfileComingSoon';

type TabId = 'basic' | 'password' | 'study' | 'notify' | 'stats' | 'danger';

const TABS: { id: TabId; label: string; comingSoon?: boolean; danger?: boolean }[] = [
  { id: 'basic', label: '기본 정보' },
  { id: 'password', label: '비밀번호' },
  { id: 'study', label: '학습 설정', comingSoon: true },
  { id: 'notify', label: '알림', comingSoon: true },
  { id: 'stats', label: '계정 통계' },
  { id: 'danger', label: '위험 영역', danger: true },
];

export default function ProfilePage() {
  const { user, isGuest } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabId) ?? 'basic';

  function selectTab(id: TabId) {
    setSearchParams({ tab: id });
  }

  return (
    <PageLayout>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>프로필 수정</h1>
          <p style={{ margin: '8px 0 0', color: 'var(--text-2)', fontSize: 14 }}>계정 정보와 학습 환경을 관리합니다.</p>
        </div>

        {isGuest ? (
          <div style={{ textAlign: 'center', padding: '80px 24px', background: 'var(--surface)', borderRadius: 16 }}>
            <Avatar username="G" size={72} fontSize={28} />
            <p style={{ marginTop: 20, fontWeight: 600, fontSize: 16 }}>게스트 계정입니다</p>
            <p style={{ color: 'var(--text-2)', marginBottom: 24 }}>회원가입 후 프로필 기능을 이용할 수 있습니다.</p>
            <Link to="/register">
              <button className="btn btn-primary">회원가입</button>
            </Link>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
            {/* 사이드바 */}
            <aside style={{ width: 180, flexShrink: 0, background: 'var(--surface)', borderRadius: 12, padding: 8 }}>
              <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => selectTab(tab.id)}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      width: '100%', padding: '10px 12px', borderRadius: 8, border: 'none',
                      background: 'transparent',
                      color: tab.danger
                        ? 'var(--danger)'
                        : activeTab === tab.id
                          ? 'var(--text)'
                          : 'var(--text-2)',
                      fontWeight: activeTab === tab.id ? 600 : 400,
                      fontSize: 14, cursor: 'pointer', textAlign: 'left',
                    }}
                  >
                    {tab.label}
                    {tab.comingSoon && (
                      <span style={{ fontSize: 10, background: 'var(--surface-3)', borderRadius: 4, padding: '1px 5px', color: 'var(--text-3)' }}>준비중</span>
                    )}
                  </button>
                ))}
              </nav>
            </aside>

            {/* 콘텐츠 */}
            <main style={{ flex: 1, background: 'var(--surface)', borderRadius: 12, padding: 32, minWidth: 0 }}>
              {activeTab === 'basic' && <ProfileBasicInfo />}
              {activeTab === 'password' && <ProfilePasswordChange />}
              {activeTab === 'study' && <ProfileComingSoon label="학습 설정" />}
              {activeTab === 'notify' && <ProfileComingSoon label="알림" />}
              {activeTab === 'stats' && <ProfileStats />}
              {activeTab === 'danger' && <ProfileDangerZone />}
            </main>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
