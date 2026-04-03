# e-Gov 法令 XML 構造ガイド

条文取得 API (`/articles` エンドポイント) のレスポンス XML 構造。

## レスポンス全体構造

```xml
<DataRoot>
  <Result>
    <Code>0</Code>
    <Message>正常終了</Message>
  </Result>
  <ApplData>
    <LawId>129AC0000000089</LawId>
    <LawNum>明治二十九年法律第八十九号</LawNum>
    <LawContents>
      <LawContentsArticle>
        <!-- 条文データ -->
      </LawContentsArticle>
    </LawContents>
  </ApplData>
</DataRoot>
```

## 条文（Article）の構造

```xml
<LawContentsArticle>
  <ArticleTitle>第七百九条</ArticleTitle>
  <ArticleCaption>（不法行為による損害賠償）</ArticleCaption>
  <Paragraph Num="1">
    <ParagraphNum/>
    <ParagraphSentence>
      <Sentence>故意又は過失によって他人の権利又は法律上保護される利益を侵害した者は、これによって生じた損害を賠償する責任を負う。</Sentence>
    </ParagraphSentence>
  </Paragraph>
</LawContentsArticle>
```

## 複数項がある場合

```xml
<Paragraph Num="1">
  <ParagraphNum>１</ParagraphNum>
  <ParagraphSentence>
    <Sentence>第一項の条文...</Sentence>
  </ParagraphSentence>
</Paragraph>
<Paragraph Num="2">
  <ParagraphNum>２</ParagraphNum>
  <ParagraphSentence>
    <Sentence>第二項の条文...</Sentence>
  </ParagraphSentence>
</Paragraph>
```

## 号（Item）がある場合

```xml
<Paragraph Num="1">
  <ParagraphNum>１</ParagraphNum>
  <ParagraphSentence>
    <Sentence>次に掲げる場合には、...</Sentence>
  </ParagraphSentence>
  <Item Num="1">
    <ItemTitle>一</ItemTitle>
    <ItemSentence>
      <Sentence>第一号の内容...</Sentence>
    </ItemSentence>
  </Item>
  <Item Num="2">
    <ItemTitle>二</ItemTitle>
    <ItemSentence>
      <Sentence>第二号の内容...</Sentence>
    </ItemSentence>
  </Item>
</Paragraph>
```

## 表示への変換ルール

| XML 要素 | 表示形式 |
|---------|---------|
| `ArticleTitle` + `ArticleCaption` | `## 法令名 第X条（見出し）` |
| `Paragraph` (1項のみ) | 項番号なしで本文表示 |
| `Paragraph` (複数項) | `１　本文...` `２　本文...` |
| `Item` | `　一　内容...` `　二　内容...` |
| `Sentence` 内の `<Ruby>` | ルビを除去してテキストのみ表示 |

## エラーレスポンス

```xml
<DataRoot>
  <Result>
    <Code>1</Code>
    <Message>該当する法令が見つかりません</Message>
  </Result>
</DataRoot>
```

`Code` が `0` 以外の場合はエラー。`Message` をユーザーに表示する。
