 // index creation

 CREATE VECTOR INDEX paragraph IF NOT EXISTS
 FOR (p:PARAGRAPH)
 ON p.embedding
 OPTIONS {
   indexConfig: {
     `vector.dimensions`: 384,
     `vector.similarity_function`: 'cosine'
   }
 };