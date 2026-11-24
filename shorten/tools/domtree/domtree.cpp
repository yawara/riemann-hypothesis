// 段階 2 の下調べ: 主定理から見た宣言の依存グラフの支配木を求め、各宣言が「それだけのために」抱えている行数を数える。
//
// 入力は rhshrink(RHSHRINK_EDGES=1)が書き出す decl-ids.tsv と decl-edges.tsv。
// 定理は「主張」の節点と「証明」の節点に分ける(主張 → 証明 の辺を足す)。辺の種類 T は主張から、V は証明から、
// D は定理でない宣言から出る。仮の根から主定理の主張へ辺を張り、Cooper–Harvey–Kennedy の反復法で直近の支配節点を求める。
// 節点 v が支配する部分木は、v を通らなければ主定理から辿り着けない宣言の集まりで、v を別の方法で示せば
// (証明の節点なら、その定理を依存の少ない証明に置き換えれば)消せる。
//
// 行数は宣言の行範囲で数え、定理は証明の節点に載せる(主張の行も含むので、少し多めに出る)。
//
// 使い方: domtree <decl-ids.tsv> <decl-edges.tsv> <出力.tsv> [主定理の名前 …]
// 出力: 節点ごとに id、名前、種類(decl / proof)、モジュール、自身の行、支配する部分木の行と宣言の数、直近の支配節点の名前
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

int main(int argc, char** argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: domtree <decl-ids.tsv> <decl-edges.tsv> <out.tsv> [roots...]\n");
    return 2;
  }
  vector<string> roots;
  for (int i = 4; i < argc; i++) roots.push_back(argv[i]);
  if (roots.empty())
    roots = {"riemannHypothesis", "riemannZeta_eq_zero_re", "LFunction_ne_zero_of_half_lt_re", "LFunction_eq_zero_re",
             "LFunction_eq_zero_re_of_isPrimitive"};

  // 宣言
  vector<string> name, module, kind;
  vector<long> lines;
  unordered_map<string, int> byName;
  {
    ifstream in(argv[1]);
    string l;
    getline(in, l);  // 見出し
    while (getline(in, l)) {
      vector<string> f;
      size_t s = 0;
      for (;;) {
        size_t t = l.find('\t', s);
        f.push_back(l.substr(s, t == string::npos ? string::npos : t - s));
        if (t == string::npos) break;
        s = t + 1;
      }
      if (f.size() < 7) continue;
      int id = stoi(f[0]);
      if ((int)name.size() <= id) {
        name.resize(id + 1);
        module.resize(id + 1);
        kind.resize(id + 1);
        lines.resize(id + 1, 0);
      }
      name[id] = f[1];
      module[id] = f[2];
      kind[id] = f[5];
      lines[id] = stol(f[4]) - stol(f[3]) + 1;
      byName[f[1]] = id;
    }
  }
  const int N = name.size();
  const int ROOT = 2 * N;
  const int V = 2 * N + 1;
  fprintf(stderr, "decls %d\n", N);

  // 辺
  vector<pair<int, int>> E;
  E.reserve(30000000);
  {
    FILE* fp = fopen(argv[2], "r");
    char buf[256];
    while (fgets(buf, sizeof buf, fp)) {
      int a, b;
      char k;
      if (sscanf(buf, "%d\t%c\t%d", &a, &k, &b) != 3) continue;
      int src = (k == 'V') ? a + N : a;
      E.push_back({src, b});
    }
    fclose(fp);
  }
  for (int i = 0; i < N; i++)
    if (kind[i] == "theorem") E.push_back({i, i + N});
  int nRoots = 0;
  for (auto& r : roots) {
    auto it = byName.find(r);
    if (it == byName.end()) {
      fprintf(stderr, "root not found: %s\n", r.c_str());
      continue;
    }
    E.push_back({ROOT, it->second});
    nRoots++;
  }
  fprintf(stderr, "edges %zu, roots %d\n", E.size(), nRoots);

  // CSR(後続と先行)
  vector<int> so(V + 1, 0), po_(V + 1, 0);
  for (auto& e : E) so[e.first + 1]++, po_[e.second + 1]++;
  for (int i = 0; i < V; i++) so[i + 1] += so[i], po_[i + 1] += po_[i];
  vector<int> succ(E.size()), pred(E.size());
  {
    vector<int> a(so.begin(), so.end() - 1), b(po_.begin(), po_.end() - 1);
    for (auto& e : E) succ[a[e.first]++] = e.second, pred[b[e.second]++] = e.first;
  }
  E.clear();
  E.shrink_to_fit();

  // 根からの深さ優先探索で、帰りがけ順の番号と、その逆順(RPO)
  vector<int> post(V, -1), order;
  order.reserve(V);
  {
    vector<char> vis(V, 0);
    vector<pair<int, int>> st;
    st.push_back({ROOT, so[ROOT]});
    vis[ROOT] = 1;
    while (!st.empty()) {
      auto& [v, i] = st.back();
      if (i < so[v + 1]) {
        int w = succ[i++];
        if (!vis[w]) {
          vis[w] = 1;
          st.push_back({w, so[w]});
        }
      } else {
        post[v] = order.size();
        order.push_back(v);
        st.pop_back();
      }
    }
  }
  fprintf(stderr, "reachable nodes %zu\n", order.size());
  vector<int> rpo(order.rbegin(), order.rend());

  // Cooper–Harvey–Kennedy
  vector<int> idom(V, -1);
  idom[ROOT] = ROOT;
  auto intersect = [&](int a, int b) {
    while (a != b) {
      while (post[a] < post[b]) a = idom[a];
      while (post[b] < post[a]) b = idom[b];
    }
    return a;
  };
  for (int round = 1;; round++) {
    bool changed = false;
    for (int v : rpo) {
      if (v == ROOT) continue;
      int nd = -1;
      for (int i = po_[v]; i < po_[v + 1]; i++) {
        int p = pred[i];
        if (post[p] < 0 || idom[p] < 0) continue;
        nd = (nd < 0) ? p : intersect(p, nd);
      }
      if (nd != idom[v]) idom[v] = nd, changed = true;
    }
    fprintf(stderr, "round %d%s\n", round, changed ? "" : " (stable)");
    if (!changed) break;
  }

  // 部分木の和(帰りがけ順で、子を先に)
  vector<long> subL(V, 0), subN(V, 0);
  for (int v : order) {
    if (v < N) subL[v] += (kind[v] == "theorem") ? 0 : lines[v], subN[v] += 1;
    else if (v < 2 * N) subL[v] += lines[v - N];
    if (v != ROOT) subL[idom[v]] += subL[v], subN[idom[v]] += subN[v];
  }
  fprintf(stderr, "total reachable lines %ld, decls %ld\n", subL[ROOT], subN[ROOT]);

  FILE* out = fopen(argv[3], "w");
  fprintf(out, "id\tdecl\tnode\tkind\tmodule\town_lines\tsub_lines\tsub_decls\tidom\tidom_node\n");
  for (int v : order) {
    if (v == ROOT) continue;
    int d = v < N ? v : v - N;
    int u = idom[v];
    string un = u == ROOT ? "(root)" : name[u < N ? u : u - N];
    const char* uk = u == ROOT ? "-" : (u < N ? "decl" : "proof");
    fprintf(out, "%d\t%s\t%s\t%s\t%s\t%ld\t%ld\t%ld\t%s\t%s\n", d, name[d].c_str(), v < N ? "decl" : "proof",
            kind[d].c_str(), module[d].c_str(), lines[d], subL[v], subN[v], un.c_str(), uk);
  }
  fclose(out);
  return 0;
}
