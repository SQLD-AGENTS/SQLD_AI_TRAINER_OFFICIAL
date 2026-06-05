import { useNavigate } from 'react-router-dom';
import TopBar from '../components/layout/TopBar';
import { authApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const FEATURES = [
  ['✦', 'DKT ZPD 추천', '근접발달영역(Zone of Proximal Development) 모델로 지금 풀기 적절한 난이도 문제를 자동 추천합니다.'],
  ['⟐', 'AI 해설 (RAG)', '유사 문제와 개념을 참조한 단계별 풀이 설명. 왜 틀렸는지, 어떻게 풀어야 하는지 자세히 안내합니다.'],
  ['◉', '취약 분석', '챕터별 정답률을 시각화하고, 오답 확률(error probability) 예측으로 위험한 영역을 미리 보여줍니다.'],
];

export default function LandingPage() {
  const navigate = useNavigate();
  const { loginAsGuest } = useAuth();

  const handleGuest = async () => {
    try {
      const res = await authApi.guest();
      loginAsGuest(res.data.access_token, res.data.user_id);
      navigate('/questions');
    } catch {
      navigate('/questions');
    }
  };

  return (
    <div className="screen">
      <TopBar />
      <div className="page is-wide" style={{ paddingTop: 48 }}>
        <div className="hero">
          <div className="t-eyebrow">✦ AI 분석 기반 SQLD 학습 플랫폼</div>
          <h1 className="t-display" style={{ marginTop: 8, marginBottom: 16 }}>
            AI가 분석하는<br />SQLD 개인화 학습.
          </h1>
          <p>
            DKT · RAG · 하이브리드 추천. 297문제, 12챕터, 5가지 AI 모델로<br />
            당신의 약점을 정확히 찾아냅니다.
          </p>
          <div className="cta-row">
            <button className="btn btn-primary btn-lg" onClick={handleGuest}>
              게스트로 시작하기
            </button>
            <button className="btn btn-outline btn-lg" onClick={() => navigate('/login')}>
              로그인
            </button>
          </div>
        </div>

        <div className="grid-3" style={{ marginTop: 24, gap: 16 }}>
          {FEATURES.map(([glyph, title, desc]) => (
            <div key={title} className="feat">
              <div className="icon-circle">{glyph}</div>
              <h3 className="t-h3">{title}</h3>
              <p>{desc}</p>
            </div>
          ))}
        </div>

        <div className="stats-bar" style={{ marginTop: 24 }}>
          <div><div className="n">297</div><div className="l">문제</div></div>
          <div className="sep"><div className="n">12</div><div className="l">챕터</div></div>
          <div className="sep"><div className="n">5</div><div className="l">AI 모델</div></div>
        </div>
      </div>
    </div>
  );
}
