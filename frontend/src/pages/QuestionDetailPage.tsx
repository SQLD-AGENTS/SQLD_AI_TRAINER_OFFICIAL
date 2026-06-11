import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../components/layout/PageLayout';
import DifficultyBadge from '../components/ui/DifficultyBadge';
import Spinner from '../components/ui/Spinner';
import AiBadge from '../components/ui/AiBadge';
import ChoiceList from '../components/question/ChoiceList';
import SqlBlock from '../components/question/SqlBlock';
import RiskIndicator from '../components/question/RiskIndicator';
import AiExplanation from '../components/question/AiExplanation';
import { questionsApi, logsApi, explainApi, predictApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

type Stage = 'pre' | 'post' | 'ai';

export default function QuestionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, isGuest } = useAuth();
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<number | null>(null);
  const [stage, setStage] = useState<Stage>('pre');
  const [explanation, setExplanation] = useState('');
  const [similarQuestions, setSimilarQuestions] = useState<Parameters<typeof AiExplanation>[0]['similarQuestions']>([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [prevIsCorrect, setPrevIsCorrect] = useState<boolean | null>(null);
  const [isFromHistory, setIsFromHistory] = useState(false);

  const qid = id ?? '';

  useEffect(() => {
    setSelected(null);
    setStage('pre');
    setExplanation('');
    setSimilarQuestions([]);
    setPrevIsCorrect(null);
    setIsFromHistory(false);
  }, [qid]);

  useEffect(() => {
    if (!qid || !user || isGuest) return;
    let cancelled = false;
    logsApi.checkSolved(qid).then((res) => {
      if (!cancelled && res.data.is_solved) {
        setPrevIsCorrect(res.data.is_correct);
        setIsFromHistory(true);
        setStage('post');
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [qid, user, isGuest]);

  const { data: question, isLoading } = useQuery({
    queryKey: ['question', qid],
    queryFn: () => questionsApi.detail(qid).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled: !!qid,
  });

  const { data: predict } = useQuery({
    queryKey: ['predict', user?.user_id, qid],
    queryFn: () => predictApi.errorProb(user!.user_id, qid).then((r) => r.data),
    enabled: !!user && !isGuest && !!qid,
  });

  const submitMutation = useMutation({
    mutationFn: ({ sel }: { sel: number }) => logsApi.submit(qid, sel),
    onSuccess: () => {
      setPrevIsCorrect(null);
      setIsFromHistory(false);
      queryClient.invalidateQueries({ queryKey: ['solved-summary'] });
      setStage('post');
    },
  });

  const handleSubmit = () => {
    if (selected === null) return;
    if (user && !isGuest) {
      submitMutation.mutate({ sel: selected });
    } else {
      setStage('post');
    }
  };

  const handleShowAI = async () => {
    setStage('ai');
    setAiLoading(true);
    try {
      const res = await explainApi.explain(qid);
      setExplanation(res.data.rag_explanation ?? '');
      setSimilarQuestions(res.data.similar_questions ?? []);
    } catch {
      setExplanation('해설을 불러오는 데 실패했습니다.');
    } finally {
      setAiLoading(false);
    }
  };

  if (isLoading) {
    return (
      <PageLayout narrow>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  if (!question) {
    return (
      <PageLayout narrow>
        <p className="t-body-2">문제를 찾을 수 없습니다.</p>
      </PageLayout>
    );
  }

  const correct = question.correct_answer != null ? Number(question.correct_answer) : null;
  const resultIsCorrect = isFromHistory && prevIsCorrect !== null ? prevIsCorrect : selected === correct;

  const choiceCount = question.choices?.length ?? (question as { choice_count?: number }).choice_count ?? 4;
  const rawChoices: { number: number; text: string }[] = Array.isArray(question.choices)
    ? question.choices
    : Array.from({ length: choiceCount }, (_, i) => ({ number: i + 1, text: `선택지 ${i + 1}` }));
  const choices = rawChoices;

  return (
    <PageLayout narrow>
      <Link to="/questions" className="link-pill" style={{ marginBottom: 16, display: 'inline-block' }}>
        ‹ 목록으로
      </Link>

      <div className="card card-pad-lg">
        <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
          <span className="tag is-light">{question.chapter_name}</span>
          {question.difficulty_label && <DifficultyBadge difficulty={question.difficulty_label} />}
          {question.question_type && <span className="tag">{question.question_type}</span>}
          <span style={{ marginLeft: 'auto' }} className="t-caption">문제 #{qid}</span>
          {stage === 'post' && (
            <span className="tag" style={{
              background: resultIsCorrect ? 'var(--success-soft)' : 'var(--danger-soft)',
              color: resultIsCorrect ? 'var(--success)' : 'var(--danger)',
            }}>
              {resultIsCorrect ? '정답' : '오답'}
            </span>
          )}
        </div>

        <p className="t-body" style={{ marginTop: 18, fontSize: 16 }}>
          {question.question_text}
        </p>

        {question.sql_content && (
          <div style={{ marginTop: 14 }}>
            <SqlBlock sql={question.sql_content} />
          </div>
        )}

        {stage === 'pre' && predict?.error_probability !== undefined && (
          <div style={{ marginTop: 16 }}>
            <RiskIndicator probability={predict.error_probability} />
          </div>
        )}

        {stage === 'pre' && !user && (
          <div className="card" style={{ marginTop: 16, background: 'var(--ai-tint)', border: '1px solid #d0e3fa' }}>
            <p className="t-body-2">
              <Link to="/login" className="link-pill">로그인</Link>하면 AI 오답 확률 예측을 확인할 수 있습니다.
            </p>
          </div>
        )}

        {stage === 'pre' && (
          <>
            <h3 className="t-h3" style={{ marginTop: 24, marginBottom: 12 }}>보기</h3>
            <ChoiceList
              choices={choices}
              selected={selected}
              mode="selecting"
              onSelect={setSelected}
            />
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 24 }}>
              <button className="btn btn-outline" onClick={() => navigate('/questions')}>건너뛰기</button>
              <button
                className="btn btn-primary btn-lg"
                onClick={handleSubmit}
                disabled={selected === null || submitMutation.isPending}
              >
                {submitMutation.isPending ? <Spinner size="sm" /> : '제출하기'}
              </button>
            </div>
          </>
        )}

        {(stage === 'post' || stage === 'ai') && (
          <>
            <h3 className="t-h3" style={{ marginTop: 20, marginBottom: 12 }}>결과</h3>
            <ChoiceList choices={choices} selected={selected} correct={correct ?? undefined} mode="result" />
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 24, gap: 12 }}>
              <div className="row gap-8">
                <button className="btn btn-outline" onClick={() => navigate('/questions')}>목록으로</button>
                {isFromHistory && (
                  <button className="btn btn-outline" onClick={() => {
                    setStage('pre');
                    setSelected(null);
                    setPrevIsCorrect(null);
                    setIsFromHistory(false);
                  }}>다시 풀기</button>
                )}
              </div>
              {stage === 'post' && (
                <button
                  className="btn btn-primary btn-lg"
                  onClick={handleShowAI}
                  style={{ flexDirection: 'column', alignItems: 'center', gap: 2 }}
                >
                  {resultIsCorrect
                    ? <span style={{ fontSize: 12, opacity: 0.85 }}>정답입니다! 계속 풀어볼까요?</span>
                    : <span style={{ fontSize: 12, opacity: 0.85 }}>오답입니다. 해설을 확인해보세요.</span>
                  }
                  <AiBadge>AI 해설 보기</AiBadge>
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {stage === 'ai' && (
        <AiExplanation
          loading={aiLoading}
          explanation={explanation}
          similarQuestions={similarQuestions}
        />
      )}

      {stage === 'ai' && (
        <div className="row" style={{ justifyContent: 'center', gap: 12, marginTop: 24 }}>
          <button className="btn btn-outline" onClick={() => navigate('/questions')}>목록으로</button>
        </div>
      )}
    </PageLayout>
  );
}
