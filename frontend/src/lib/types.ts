export type ArticleFormat = "summary" | "deep_dive" | "analysis";
export type InterviewStatus =
  | "pending"
  | "downloading"
  | "transcribing"
  | "analyzing"
  | "generating"
  | "completed"
  | "failed";

export interface UserPublic {
  id: string;
  full_name: string | null;
  bio: string | null;
  role: "user" | "analyst" | "admin";
  is_verified_analyst: boolean;
  reputation: number;
}

export interface UserMe extends UserPublic {
  email: string;
  tier: "free" | "premium";
  is_premium: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserMe;
}

export interface Citation {
  quote: string;
  speaker: string | null;
  timestamp: number | null;
  url: string;
  verified: boolean;
}

export interface ArticleListItem {
  id: string;
  slug: string;
  format: ArticleFormat;
  is_premium: boolean;
  headline: string;
  meta_description: string;
  summary: string;
  tags: string[];
  tickers: string[];
  reading_time_minutes: number;
  published_at: string | null;
  interview_id: string | null;
  author: UserPublic | null;
}

export interface Article extends ArticleListItem {
  status: "draft" | "published" | "archived";
  content: string | null;
  citations: Citation[];
  citation_accuracy: number | null;
  view_count: number;
  is_locked: boolean;
  source_url: string | null;
  source_title: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface KeyQuote {
  quote: string;
  speaker: string | null;
  timestamp: number | null;
  context: string | null;
  verified: boolean;
}

export interface Insight {
  insight: string;
  category?: string;
  confidence?: string;
}

export interface InterviewListItem {
  id: string;
  youtube_url: string;
  youtube_video_id: string;
  status: InterviewStatus;
  title: string | null;
  channel: string | null;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  published_at: string | null;
  topics: { name: string; slug: string }[];
  companies: { name: string; ticker: string | null }[];
  created_at: string;
}

export interface Interview extends InterviewListItem {
  error_message: string | null;
  description: string | null;
  summary: string | null;
  speakers: { name: string; role?: string }[];
  key_quotes: KeyQuote[];
  insights: Insight[];
  sentiment: string | null;
  processed_at: string | null;
}

export interface Comment {
  id: string;
  article_id: string;
  parent_id: string | null;
  body: string;
  score: number;
  is_deleted: boolean;
  created_at: string;
  user: UserPublic;
  my_vote: number;
}

export interface Follow {
  id: string;
  follow_type: "company" | "topic";
  value: string;
  display_name: string | null;
  created_at: string;
}

export interface Holding {
  id: string;
  ticker: string;
  shares: string;
  average_cost: string | null;
  notes: string | null;
  created_at: string;
}

export interface Portfolio {
  holdings: Holding[];
  total_cost_basis: string;
  related_articles: ArticleListItem[];
}

export interface Plan {
  tier: "free" | "premium";
  name: string;
  price_monthly_usd: number;
  features: string[];
}

export interface AnalystApplication {
  id: string;
  user_id: string;
  credentials: string;
  links: string | null;
  status: "pending" | "approved" | "rejected";
  review_notes: string | null;
  created_at: string;
}
