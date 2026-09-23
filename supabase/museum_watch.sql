-- 美術館ウォッチ: 端末間同期用のテーブル（グルメレコメンドアプリと同じ Supabase プロジェクトに相乗りする）
-- Supabase ダッシュボード → SQL Editor にこの内容を貼って Run する（1 回だけ。何度実行しても同じ結果になる）

create table if not exists public.museum_watch_state (
  user_id    uuid   primary key default auth.uid() references auth.users (id) on delete cascade,
  data       jsonb  not null default '{}'::jsonb,  -- { visits, wants, origin, updatedAt }
  updated_at bigint not null                        -- 端末側の更新時刻（ミリ秒）
);

-- 自分の行しか読めない・書けない
alter table public.museum_watch_state enable row level security;
drop policy if exists "own row" on public.museum_watch_state;
create policy "own row" on public.museum_watch_state
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
