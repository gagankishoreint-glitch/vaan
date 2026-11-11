# Flagged chunks (109 of 379)

## `attn-v7:s3:c0000` p.2 [caption] digit_ratio=0.017
```
Most competitive neural sequence transduction models have an encoder-decoder structure [5, 2, 35].
Here, the encoder maps an input sequence of symbol representations (x1, ..., xn) to a sequence
of continuous representations z = (z1, ..., zn). Given z, the decoder then generates an output
sequence (y1, ..., ym) of symbols one element at a time. At each step the model is auto-regressive
[10], consuming the previously generated symbols as additional input when generating the next.
Figure 1: The Transformer - model architecture.
The Transformer follows this overall architecture using stacked self-attention and point-wise, fully
connected layers for both the encoder and decoder, shown in the left and right halves of Figure 1,
respectively.
```

## `attn-v7:s3.2:c0000` p.3 [caption] digit_ratio=0.002
```
An attention function can be described as mapping a query and a set of key-value pairs to an output,
where the query, keys, values, and output are all vectors. The output is computed as a weighted sum
Scaled Dot-Product Attention
Multi-Head Attention
Figure 2: (left) Scaled Dot-Product Attention. (right) Multi-Head Attention consists of several
attention layers running in parallel.
of the values, where the weight assigned to each value is computed by a compatibility function of the
query with the corresponding key.
```

## `attn-v7:s3.2.1:c0000` p.4 [equation] digit_ratio=0.003
```
We call our particular attention "Scaled Dot-Product Attention" (Figure 2). The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values.
In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V . We compute
the matrix of outputs as:
Attention(Q, K, V ) = softmax(QKT
√dk
(1)
The two most commonly used attention functions are additive attention [2], and dot-product (multi-
plicative) attention. Dot-product attention is identical to our algorithm, except for the scaling factor
√dk . Additive attention compu
```

## `attn-v7:s3.2.2:c0000` p.4 [caption] digit_ratio=0.008
```
Instead of performing a single attention function with dmodel-dimensional keys, values and queries,
we found it beneficial to linearly project the queries, keys and values h times with different, learned
linear projections to dk, dk and dv dimensions, respectively. On each of these projected versions of
queries, keys and values we then perform the attention function in parallel, yielding dv-dimensional
4To illustrate why the dot products get large, assume that the components of q and k are independent random
variables with mean 0 and variance 1. Then their dot product, q · k = Pdk
i=1 qiki, has mean 0 and variance dk.
output values. These are concatenated and once again projected, resulting in the final values, as
depicted in Figure 2.
Multi-head attention allows the model to jointly atten
```

## `attn-v7:s3.2.2:c0001` p.4 [equation] digit_ratio=0.009
```
headi = Attention(QW Q
i , KW K
i , V W V
i )
Where the projections are parameter matrices W Q
∈Rdmodel×dk, W K
∈Rdmodel×dk, W V
∈Rdmodel×dv
and W O ∈Rhdv×dmodel.
In this work we employ h = 8 parallel attention layers, or heads. For each of these we use
dk = dv = dmodel/h = 64. Due to the reduced dimension of each head, the total computational cost
is similar to that of single-head attention with full dimensionality.
```

## `attn-v7:s3.2.3:c0000` p.5 [caption] digit_ratio=0.005
```
The Transformer uses multi-head attention in three different ways:
• In "encoder-decoder attention" layers, the queries come from the previous decoder layer,
and the memory keys and values come from the output of the encoder. This allows every
position in the decoder to attend over all positions in the input sequence. This mimics the
typical encoder-decoder attention mechanisms in sequence-to-sequence models such as
[38, 2, 9].
• The encoder contains self-attention layers. In a self-attention layer all of the keys, values
and queries come from the same place, in this case, the output of the previous layer in the
encoder. Each position in the encoder can attend to all positions in the previous layer of the
encoder.
• Similarly, self-attention layers in the decoder allow each position in the
```

## `attn-v7:s3.3:c0000` p.5 [equation] digit_ratio=0.027
```
In addition to attention sub-layers, each of the layers in our encoder and decoder contains a fully
connected feed-forward network, which is applied to each position separately and identically. This
consists of two linear transformations with a ReLU activation in between.
FFN(x) = max(0, xW1 + b1)W2 + b2
(2)
While the linear transformations are the same across different positions, they use different parameters
from layer to layer. Another way of describing this is as two convolutions with kernel size 1.
The dimensionality of input and output is dmodel = 512, and the inner-layer has dimensionality
dff = 2048.
```

## `attn-v7:s3.4:c0000` p.5 [caption] digit_ratio=0.012
```
Similarly to other sequence transduction models, we use learned embeddings to convert the input
tokens and output tokens to vectors of dimension dmodel. We also use the usual learned linear transfor-
mation and softmax function to convert the decoder output to predicted next-token probabilities. In
our model, we share the same weight matrix between the two embedding layers and the pre-softmax
linear transformation, similar to [30]. In the embedding layers, we multiply those weights by √dmodel.
Table 1: Maximum path lengths, per-layer complexity and minimum number of sequential operations
for different layer types. n is the sequence length, d is the representation dimension, k is the kernel
size of convolutions and r the size of the neighborhood in restricted self-attention.
Layer Type
Comp
```

## `attn-v7:s5:c0000` p.7 [short] digit_ratio=0.0
```
This section describes the training regime for our models.
```

## `attn-v7:s5.3:c0000` p.7 [equation] digit_ratio=0.061
```
We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = 10−9. We varied the learning
rate over the course of training, according to the formula:
lrate = d−0.5
model · min(step_num−0.5, step_num · warmup_steps−1.5)
(3)
This corresponds to increasing the learning rate linearly for the first warmup_steps training steps,
and decreasing it thereafter proportionally to the inverse square root of the step number. We used
warmup_steps = 4000.
```

## `attn-v7:s5.4:c0000` p.7 [numeric_dense,caption] digit_ratio=0.177
```
We employ three types of regularization during training:
Table 2: The Transformer achieves better BLEU scores than previous state-of-the-art models on the
English-to-German and English-to-French newstest2014 tests at a fraction of the training cost.
Model
BLEU
Training Cost (FLOPs)
EN-DE
EN-FR
EN-DE
EN-FR
ByteNet [18]
23.75
Deep-Att + PosUnk [39]
39.2
1.0 · 1020
GNMT + RL [38]
24.6
39.92
2.3 · 1019
1.4 · 1020
ConvS2S [9]
25.16
40.46
9.6 · 1018
1.5 · 1020
MoE [32]
26.03
40.56
2.0 · 1019
1.2 · 1020
Deep-Att + PosUnk Ensemble [39]
40.4
8.0 · 1020
GNMT + RL Ensemble [38]
26.30
41.16
1.8 · 1020
1.1 · 1021
ConvS2S Ensemble [9]
26.36
41.29
7.7 · 1019
1.2 · 1021
Transformer (base model)
27.3
38.1
3.3 · 1018
Transformer (big)
28.4
41.8
2.3 · 1019
Residual Dropout
We apply dropout [33] to the output
```

## `attn-v7:s6.1:c0000` p.8 [caption] digit_ratio=0.04
```
On the WMT 2014 English-to-German translation task, the big transformer model (Transformer (big)
in Table 2) outperforms the best previously reported models (including ensembles) by more than 2.0
BLEU, establishing a new state-of-the-art BLEU score of 28.4. The configuration of this model is
listed in the bottom line of Table 3. Training took 3.5 days on 8 P100 GPUs. Even our base model
surpasses all previously published models and ensembles, at a fraction of the training cost of any of
the competitive models.
On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41.0,
outperforming all of the previously published single models, at less than 1/4 the training cost of the
previous state-of-the-art model. The Transformer (big) model trained for English-to-
```

## `attn-v7:s6.2:c0000` p.8 [numeric_dense,caption] digit_ratio=0.225
```
To evaluate the importance of different components of the Transformer, we varied our base model
in different ways, measuring the change in performance on English-to-German translation on the
5We used values of 2.8, 3.7, 6.0 and 9.5 TFLOPS for K80, K40, M40 and P100, respectively.
Table 3: Variations on the Transformer architecture. Unlisted values are identical to those of the base
model. All metrics are on the English-to-German translation development set, newstest2013. Listed
perplexities are per-wordpiece, according to our byte-pair encoding, and should not be compared to
per-word perplexities.
dmodel
dff
Pdrop
ϵls
train
PPL
BLEU
params
steps
(dev)
(dev)
×106
base
512
2048
0.1
0.1
100K
4.92
25.8
(A)
512
512
5.29
24.9
128
128
5.00
25.5
4.91
25.8
5.01
25.4
(B)
5.16
25.1
5.01
25.4
(C)
6.11
```

## `attn-v7:s6.2:c0001` p.8 [caption] digit_ratio=0.048
```
4.92
25.7
big
1024
4096
0.3
300K
4.33
26.4
213
development set, newstest2013. We used beam search as described in the previous section, but no
checkpoint averaging. We present these results in Table 3.
In Table 3 rows (A), we vary the number of attention heads and the attention key and value dimensions,
keeping the amount of computation constant, as described in Section 3.2.2. While single-head
attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads.
In Table 3 rows (B), we observe that reducing the attention key size dk hurts model quality. This
suggests that determining compatibility is not easy and that a more sophisticated compatibility
function than dot product may be beneficial. We further observe in rows (C) and (D) that, as expected,
bigger mod
```

## `attn-v7:s6.3:c0000` p.9 [caption] digit_ratio=0.024
```
To evaluate if the Transformer can generalize to other tasks we performed experiments on English
constituency parsing. This task presents specific challenges: the output is subject to strong structural
constraints and is significantly longer than the input. Furthermore, RNN sequence-to-sequence
models have not been able to attain state-of-the-art results in small-data regimes [37].
We trained a 4-layer transformer with dmodel = 1024 on the Wall Street Journal (WSJ) portion of the
Penn Treebank [25], about 40K training sentences. We also trained it in a semi-supervised setting,
using the larger high-confidence and BerkleyParser corpora from with approximately 17M sentences
[37]. We used a vocabulary of 16K tokens for the WSJ only setting and a vocabulary of 32K tokens
for the semi-supervise
```

## `attn-v7:s6.3:c0001` p.9 [caption] digit_ratio=0.109
```
parameters
remained unchanged from the English-to-German base translation model. During inference, we
Table 4: The Transformer generalizes well to English constituency parsing (Results are on Section 23
of WSJ)
Parser
Training
WSJ 23 F1
Vinyals & Kaiser el al. (2014) [37]
WSJ only, discriminative
88.3
Petrov et al. (2006) [29]
WSJ only, discriminative
90.4
Zhu et al. (2013) [40]
WSJ only, discriminative
90.4
Dyer et al. (2016) [8]
WSJ only, discriminative
91.7
Transformer (4 layers)
WSJ only, discriminative
91.3
Zhu et al. (2013) [40]
semi-supervised
91.3
Huang & Harper (2009) [14]
semi-supervised
91.3
McClosky et al. (2006) [26]
semi-supervised
92.1
Vinyals & Kaiser el al. (2014) [37]
semi-supervised
92.1
Transformer (4 layers)
semi-supervised
92.7
Luong et al. (2015) [23]
multi-task
93.0
```

## `attn-v7:s7:c0008` p.10 [caption] digit_ratio=0.024
```
Yue Zhang, Wenliang Chen, Min Zhang, and Jingbo Zhu. Fast and accurate
shift-reduce constituent parsing. In Proceedings of the 51st Annual Meeting of the ACL (Volume
1: Long Papers), pages 434–443. ACL, August 2013.
Attention Visualizations
this
spirit
that
majority
American
governments
have
passed
new
laws
since
2009
making
the
registration
voting
process
more
difficult
<EOS>
<pad>
<pad>
<pad>
<pad>
<pad>
<pad>
this
spirit
that
majority
American
governments
have
passed
new
laws
since
2009
making
the
registration
voting
process
more
difficult
<EOS>
<pad>
<pad>
<pad>
<pad>
<pad>
<pad>
Figure 3: An example of the attention mechanism following long-distance dependencies in the
encoder self-attention in layer 5 of 6. Many of the attention heads attend to a distant dependency of
the verb ‘makin
```

## `attn-v7:s7:c0009` p.10 [caption] digit_ratio=0.007
```
its
application
should
just
this
what
are
missing
opinion
<EOS>
<pad>
The
Law
will
never
perfect
but
its
application
should
just
this
what
are
missing
opinion
<EOS>
<pad>
The
Law
will
never
perfect
but
its
application
should
just
this
what
are
missing
opinion
<EOS>
<pad>
The
Law
will
never
perfect
but
its
application
should
just
this
what
are
missing
opinion
<EOS>
<pad>
Figure 4: Two attention heads, also in layer 5 of 6, apparently involved in anaphora resolution. Top:
Full attentions for head 5. Bottom: Isolated attentions from just the word ‘its’ for attention heads 5
and 6. Note that the attentions are very sharp for this word.
The
Law
will
never
perfect
but
its
application
should
just
this
what
are
missing
opinion
<EOS>
<pad>
The
Law
will
never
perfect
but
its
application
should
just

```

## `attn-v7:s7:c0010` p.10 [caption] digit_ratio=0.011
```
just
this
what
are
missing
opinion
<EOS>
<pad>
Figure 5: Many of the attention heads exhibit behaviour that seems related to the structure of the
sentence. We give two such examples above, from two different heads from the encoder self-attention
at layer 5 of 6. The heads clearly learned to perform different tasks.
```

## `moshi-v1:s2:c0007` p.4 [caption] digit_ratio=0.005
```
in real
time and allow for long conversations in full-duplex—the model always listens and can speak
at any moment; 2) it should be speech-to-speech to handle paralinguistic communication;
3) it should display knowledge and reasoning abilities that make it amenable to helpful and
enjoyable conversations. Spectron benefits from its underlying text LLM (as measured by
spoken question answering), however it is not compatible with real-time generation due to
Chain-of-Modality. PSLM proposes generating speech and text tokens in parallel to reduce
this latency, however it reduces the quality of answers, and the model still relies on ASR,
which removes paralinguistic information. More importantly, these models cannot handle
full-duplex communication, where there is no boundary between speaker turn
```

## `moshi-v1:s3.1:c0000` p.6 [caption] digit_ratio=0.011
```
Moshi is a multi-stream speech-to-speech Transformer model, which allows for full-duplex
spoken dialogue with a user thanks to an innovative architecture summarized in Figure 1.
Moshi: a speech-text foundation model for real-time dialogue
Moshi is built on top of Helium, a text LLM which we build from scratch (Section 3.2),
relying on high-quality text data to provide strong reasoning abilities to the model. We also
propose Inner Monologue (Section 3.4.4), a training and inference procedure in which we
jointly model text and audio tokens. This allows the model to fully exploit the knowledge
imparted from the text modality, while remaining a speech-to-speech system. To enable
real-time dialogue, we also design Moshi as a multi-stream architecture from the get-go
(Section 3.4.3): The model i
```

## `moshi-v1:s3.2.2:c0000` p.7 [caption] digit_ratio=0.009
```
Training data is one of the critical ingredients to train LLMs: we now describe our method to
obtain a large and high-quality text dataset. We start from high-quality data sources, such
as Wikipedia, Stack Exchange and a large collection of scientific articles. As the quantity
of data from these sources is too small to train a LLM, we also rely on web crawled data,
specifically from CommonCrawl, to extend our dataset. See more details on data sources in
Section 4.1. Web data requires extensive processing to obtain a high-quality training set:
we perform deduplication, language identification and quality filtering. In the following, we
describe each operation in more details.
Moshi: a speech-text foundation model for real-time dialogue
Table 1: Models’ hyperparameters. Hyperparameters for t
```

## `moshi-v1:s3.3.1:c0000` p.9 [caption] digit_ratio=0.039
```
Our baseline architecture takes inspiration from SoundStream (Zeghidour et al., 2022) and
Encodec (D´efossez et al., 2023) and consists of a SeaNet (Tagliasacchi et al., 2020) autoen-
coder and a Residual Vector Quantizer (Zeghidour et al., 2022). The encoder projects a
single-channel waveform x ∈RL to a latent representation enc(x) ∈RS×D by cascading
residual convolutional blocks that interleave dilated (van den Oord et al., 2016) and strided
convolutions along with ELU (Clevert et al., 2016) non-linearities and Weight Normaliza-
Moshi: a speech-text foundation model for real-time dialogue
Figure 2: Architecture and training of Mimi, our neural audio codec, with its
split residual vector quantization. During training (blue part, top), we distill non-
causal embeddings from WavLM (Chen et 
```

## `moshi-v1:s3.3.1:c0006` p.9 [short] digit_ratio=0.006
```
based on afore-
mentioned metrics. Subjective evaluations reported in Table 4 confirm this observation and
demonstrate a remarkable boost in audio quality from training with adversarial losses only.
```

## `moshi-v1:s3.4.1:c0001` p.12 [equation,caption] digit_ratio=0.015
```
with around 3 to 4 text tokens per second.
We are interested in modeling not just a single sequence (Us), but multiple sub-sequences,
e.g. different audio codebooks, along with an optional text stream. We can stack those
sub-sequences as Vs,k for 1 ≤s ≤S and 1 ≤k ≤K. Similarly, we define V0,k = 0, a
deterministic initial token value for all sub-sequences. For each 1 ≤s ≤S and 1 ≤k ≤K,
Vs,k ∈{1, . . . , Nk}, where Nk is the cardinality of the k-th sub-sequence. One can flatten
Moshi: a speech-text foundation model for real-time dialogue
Figure 3: Architecture of the RQ-Transformer. The RQ-Transformer breaks down a
flattened sequence of length K · S into S timesteps for a large Temporal Transformer which
produces a context embedding used to condition a smaller Depth Transformer over K steps.
```

## `moshi-v1:s3.4.1:c0002` p.12 [equation,caption] digit_ratio=0.024
```
illustration.
the K sequences into a single one, increasing the number of predictions by K. Lee et al.
(2022) propose using a smaller autoregressive model along the dimension K, combined with
a larger model along the time dimension, forming a RQ-Transformer. Later, Yu et al. (2024)
suggested a similar approach for byte-level modeling.
RQ-Transformer.
Formally, the RQ-Transformer consists in two Transformer models,
as illustrated in Figure 3. It consists of a Temporal Transformer, e.g. with the same archi-
tecture as the one described for Helium in Section 3.2, and a smaller Depth Transformer.
We denote TrTemp the function represented by the Temporal Transformer, and TrDepth
the one for the Depth Transformer. For simplicity, and for all steps s ≤S, we denote
Vs = (Vs,1, . . . , Vs,K) the jo
```

## `moshi-v1:s3.4.1:c0003` p.12 [equation] digit_ratio=0.028
```
we further take a sub-sequence index 1 < k ≤K, the Depth Transformer maps both zs
along with (Vs,1, . . . , Vs,k−1) to the logits estimate
ls,k = TrDepth(zs, Vs,1, . . . , Vs,k−1) ∈RNk.
(2)
We further define ls,1 = Lin(zs) ∈RN1, with Lin a dedicated linear layer. We train TrTemp,
TrDepth and Lin so that softmax(ls,k) is a good approximation of the distribution of Vs,k
conditioned on all sub-sequences for the previous steps, and of the previous sub-sequences
for the current step, e.g.
softmax(ls,1)
≈P [Vs,1|V0, . . . , Vs−1]
softmax(ls,k)
≈P [Vs,k|V0, . . . , Vs−1, Vs,1, . . . Vs,k−1]
if k > 1.
(3)
Importantly, the number of steps in the Temporal Transformer is always equal to S, rather
than K · S, and the number of steps in the Depth Transformer is at most K. In practice,
Moshi: a speech-t
```

## `moshi-v1:s3.4.2:c0000` p.14 [equation] digit_ratio=0.026
```
The audio codec Mimi described in Section 3.3 outputs Q sub-sequences, with 12.5 steps
per second of audio. We denote those sequences by At,q ∈{1, . . . , NA} for 1 ≤t ≤T with
T = 12.5 · duration, and 1 ≤q ≤Q with Q = 8. We insert the audio sub-sequences into
the multi-sequence V modeled by the RQ-Transformer. Remember that the first codebook
At,1 corresponds to the semantic information, as detailed in Section 3.3.2, while the other
codebooks correspond to acoustic features.
Acoustic delay.
We first experimented with simply setting V = A in the modeling.
However we find that introducing a slight delay between the semantic and acoustic tokens led
to more stable generations. Copet et al. (2023) show that this leads to reduced dependencies
between the sub-sequences for a given time step, cond
```

## `moshi-v1:s3.4.3:c0000` p.14 [caption] digit_ratio=0.004
```
Modeling a single stream of audio is not sufficient to fully model a conversation. Our frame-
work can be extended to modeling a two-speaker conversation: given two streams of audios
Moshi: a speech-text foundation model for real-time dialogue
Hello,
PAD
EPAD
oshi
PAD
PAD
...
...
...
...
...
...
...
...
...
...
Acoustic
tokens
Semantic
tokens
Text
tokens
Moshi stream
(speaks)
PAD
PAD
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
...
User stream
(listens)
Hello, I'm Moshi.
Hey Moshi!
Acoustic
tokens
Semantic
tokens
Figure 4: Representation of the joint sequence modeled by Moshi. Each column
represents the tokens for a given step in the joint sequence (Vs,k) described in Equation 6
with an acoustic delay τ = 1, e.g. the input of the Temporal Transfor
```

## `moshi-v1:s3.4.4:c0004` p.15 [equation,caption] digit_ratio=0.029
```
together the multi-stream and inner
monologue, we have the final set V of sequences to model defined as
Vs,1
= Ws
aligned text tokens.
Vs,2
= As,1
semantic tokens of Moshi.
Vs,1+q
= As−τ,q
s ≥τ + 1, 1 < q ≤Q
delayed acoustic tok. of Moshi.
Vs,1+Q+1
= A′
s,1
semantic tokens of other.
Vs,1+Q+q
= A′
s−τ,q
s ≥τ + 1, 1 < q ≤Q
delayed acoustic tok. of other,
(6)
Moshi: a speech-text foundation model for real-time dialogue
amounting to a total number of K = 2Q + 1 streams, with Q = 8 in the experiments. A
summary is provided in Figure 4.
Inference of Moshi.
The joint sequence given by Equation 6 is the target for our model-
ing task at train time: At any time step s, the model is input with 0, V1, . . . , Vs−1 and output
an estimated probability distribution ˆVs(0, V1, . . . , Vs−1). At inference
```

## `moshi-v1:s4.1:c0000` p.17 [numeric_dense] digit_ratio=0.17
```
Our training dataset is made of a mix of high-quality data sources and filtered web data
from CommonCrawl. More specifically, 12.5% of our dataset is from the following curated
sources: Wikipedia,9 Wikibooks, Wikisource, Wikinews, StackExchange10 and the collec-
tion of scientific articles pes2o.11 Instead of doing multiple passes on Wikipedia, we use five
different dumps from 2017, 2018, 2019, 2021 and 2022. The remaining 87.5% of our dataset
is from CommonCrawl, and was filtered with the pipeline described in Section 3.2.2. We
used the following ten crawls: 2018-30, 2019-04, 2019-30, 2020-05, 2020-34, 2021-04,
2021-31, 2022-05, 2022-33, 2023-40.
```

## `moshi-v1:s4.3:c0000` p.18 [caption] digit_ratio=0.012
```
Early experiments using text-based instruct datasets such as Open Hermes (Teknium, 2023)
proved to be ill-suited for the instruct tuning of a spoken conversational system. In partic-
ular, the data formatting was often impossible to properly render with TTS (e.g. URLs),
and the format of the questions and responses was not following a natural oral flow (e.g.
bullet points, long enumerations). Instead, we leverage Helium, fine-tuned on Open Hermes
and transcripts of real conversations, to generate realistic interactions between a speech-
based AI model and a user. We then synthesize them with our multi-stream streaming
TTS described in Appendix C, leading to more than 20k hours of synthetic speech data.
To give Moshi its own consistent voice, we also condition the TTS engine on the voice of
```

## `moshi-v1:s4.4:c0000` p.20 [caption] digit_ratio=0.038
```
Helium pre-training.
An overview of the training stages and hyper parameters is pro-
vided in Table 1. For every training phase, we use AdamW (Loshchilov and Hutter, 2019),
with a weight decay of 0.1, a momentum decay of 0.9, and a decay for the online average
of the squared gradient of 0.95. All models are trained on H100 GPUs, using FSDP and
activation checkpointing. The core text-only language model, Helium, is trained for 500k
steps, with a batch size of 4.2M tokens, using a cosine learning rate schedule starting at
3 · 10−4 with linear warmup.
Moshi pre-training.
Then, we initialize the Temporal Transformer in Moshi with He-
lium, while the Depth Transformer described in Section 3.4.1 is randomly initialized. We
first train on the unsupervised audio dataset presented in Section 4.2, u
```

## `moshi-v1:s5.1:c0000` p.21 [caption] digit_ratio=0.04
```
Metrics.
We evaluate Helium (trained only on text data) on the following standard bench-
marks: AI2 Reasoning Challenge (Clark et al., 2018, ARC), Open-Book QA (Mihaylov
et al., 2018, OBQA), HellaSwag (Zellers et al., 2019, HS), WinoGrande (Sakaguchi et al.,
2021, WG), Physical Interaction QA (Bisk et al., 2020, PIQA), Social Interaction QA (Sap
et al., 2019), TriviaQA (Joshi et al., 2017, TQA), Natural Questions (Kwiatkowski et al.,
2019, NQ) and Massive Multitask Language Understanding benchmark (Hendrycks et al.,
2020, MMLU). These benchmarks cover a wide variety of tasks, including common sense
reasoning, closed-book question answering or multiple choice question answering from high
school and college subjects. We follow the evaluation protocol from previous work such as
GPT-3 or Llama
```

## `moshi-v1:s5.1:c0001` p.21 [numeric_dense,caption] digit_ratio=0.212
```
foundation model for real-time dialogue
Table 2: Text language model evaluation. Performance on standard benchmarks for
evaluating large language models, including closed book question answering, reasoning and
multiple choice QA exams. We report in bold the best performing model trained on less
than 2.5T tokens.
ARCe
ARCc
OBQA
PIQA
SIQA
TQA
MMLU
Helium
79.6
55.9
53.6
76.3
70.0
79.4
51.0
59.9/72.6
23.3
54.3
MPT
70.5
46.5
51.4
77.6
69.9
80.6
48.5
-/61.2
20.8
30.8
Falcon
73.7
47.5
53.0
76.3
68.9
80.3
47.2
-/64.6
21.0
28.0
Llama 2
75.2
45.9
58.6
77.2
69.2
78.8
48.3
-/72.1
25.7
45.3
OLMo
67.2
42.5
50.0
75.5
69.8
77.5
-/-
52.0
Mistral
80.5
54.9
52.2
81.0
74.2
82.2
47.0∗
62.5/-
23.2
62.5
Gemma 1
81.5
53.2
52.8
81.2
72.3
81.2
51.8
63.4/-
23.0
64.3
Table 3: Ablation study on hyperparameters of the 
```

## `moshi-v1:s5.1:c0003` p.21 [caption] digit_ratio=0.017
```
weights models that
are trained using significantly more compute than Helium.
Results.
We report results in Table 2, and we observe that on most benchmarks, He-
lium is on-par or outperforming models using similar amount of training compute. Even
compared to Mistral and Gemma, which use up to 3x more compute for training, Helium
obtains competitive results on some benchmarks such as ARC, Open-Book QA or Natural
Questions. This validates the quality of our pre-training text data.
Moshi: a speech-text foundation model for real-time dialogue
Table 4: Audio quality evaluation. Objective and subjective (MUSHRA) evaluation of
audio quality for baseline neural audio codecs—RVQGAN (Kumar et al., 2024), Seman-
tiCodec (Liu et al., 2024), and SpeechTokenizer
(Zhang et al., 2024b)— and the most
impor
```

## `moshi-v1:s5.1:c0004` p.21 [numeric_dense] digit_ratio=0.235
```
the codec frame rate. Both Mimi codecs are trained with
distillation, and either with the same combination of reconstruction and adversarial losses
as Encodec (see Section 3.3) or adversarial losses only.
Model
bitrate
causal
ABX (↓)
VisQOL (↑)
MOSNet (↑)
MUSHRA (↑)
Ground Truth
24kHz
3.08
90.6±1.0
RVQGAN
24kHz
75Hz
1.5kbps
1.74
2.74
31.3±1.3
SemantiCodec
16kHz
50Hz
1.3kbps
42.2%
2.43
3.12
64.8±1.5
SpeechTokenizer
16kHz
50Hz
1.5kbps
3.3%
1.53
2.67
45.1±1.5
SpeechTokenizer
16kHz
50Hz
4.0kbps
3.3%
3.07
3.10
74.3±1.5
Mimi, adv. loss only
24kHz
12.5Hz
1.1kbps
8.7%
1.84
3.10
81.0±1.3
Same, downsampled at 16kHz
16kHz
12.5Hz
1.1kbps
77.7±1.4
Mimi, non adv. only
24kHz
12.5Hz
1.1kbps
8.1%
2.82
2.89
58.8±1.8
```

## `moshi-v1:s5.2:c0005` p.23 [caption] digit_ratio=0.001
```
latency of Moshi, since generating one temporal frame of audio tokens with Moshi
requires a full forward pass through the Temporal Transformer. Finally, both RVQGAN
and SemantiCodec are non-causal, while Mimi is fully causal and thus compatible with
streaming inference and modeling of real-time conversations.
Discussion.
Mimi overall provides high reconstruction quality while encoding semantic
information, being fully causal, and operating at low framerate and bitrate. In consequence,
Mimi proves to be a well-fitted audio tokenizer to train real-time audio language models.
A collateral finding of our study is a concerning lack of correlation between objective and
subjective audio quality metrics. In particular, while we find VisQOL to provide a reliable
proxy for perceived quality when mod
```

## `moshi-v1:s5.2:c0006` p.23 [caption] digit_ratio=0.054
```
underscores the open
challenge of designing reliable objective proxies for perceived quality.
Moshi: a speech-text foundation model for real-time dialogue
Table 5: Ablation study on the use of the RQ-Transformer. All models are initialized
with Helium and pretrained on audio. When not using RQ-Transformer, we predict the 8
levels of tokens with independent classification heads, following Copet et al. (2023). Note
that perplexities are only comparable between models with a given delay, as the classification
task is easier with more delay for higher tokens.
Acoustic Delay
RQ-Transformer
Perplexity
[0, 1, 2, 3, 4, 5, 6, 7]
42.2
[0, 1, 2, 3, 4, 5, 6, 7]
40.3
[0, 2, 2, 2, 2, 2, 2, 2]
135.4
[0, 2, 2, 2, 2, 2, 2, 2]
36.8
Table 6: Ablation study on delay patterns, weight of the semantic token and

```

## `moshi-v1:s5.2:c0007` p.23 [numeric_dense] digit_ratio=0.191
```
the text token when using Inner Monologue) to 1. As different
delay patterns cannot be compared in terms of perplexity, we generate continuations from
3s prompts on the valid set, convert them into transcripts with Whisper (Radford et al.,
2023) and report their negative log-likelihood with LiteLlama-460M-1T13 along with their
length (in characters) as proxies for linguistic quality.
Acoustic
Semantic Token
Depthwise
Inner
Transcript
Transcript
Delay
Weight
Parametrization
Monologue
NLL (↓)
Length (↑)
[0, 0, 0, 0, 0, 0, 0, 0]
1.0
4.36
486
[0, 1, 1, 1, 1, 1, 1, 1]
1.0
4.12
529
[0, 2, 2, 2, 2, 2, 2, 2]
1.0
4.09
519
[0, 2, 2, 2, 2, 2, 2, 2]
100.0
3.75
538
[0, 2, 2, 2, 2, 2, 2, 2]
100.0
3.65
602
[0, 2, 2, 2, 2, 2, 2, 2]
100.0
2.77
1920
```

## `moshi-v1:s5.4:c0000` p.26 [caption] digit_ratio=0.111
```
Metrics.
We first measure the ability of Moshi to model speech sequences when being
trained for next token prediction on large scale audio data. To do so, we rely on “textless
NLP” (Lakhotia et al., 2021) metrics that evaluate an audio language model’s linguistic
knowledge by comparing likelihoods of positive and negative speech examples represented
Moshi: a speech-text foundation model for real-time dialogue
Table 7: Performance of audio and text language modeling. We report accuracies
based on scoring with negative log-likelihood, normalized by sequence length. MMLU is
evaluated in a 5-shot setting. Reusing the terminology of Nguyen et al. (2024), ∅represents
unsupported modalities while - represents unreported numbers.
Audio metrics
Text metrics
Model
sWUGGY
sBLIMP
sTopic-StoryCloze
sSt
```

## `moshi-v1:s5.4:c0007` p.26 [caption] digit_ratio=0.061
```
lexical variety or intelligibility when finetuning the model, which contra-
dicts the reduction in sWUGGY. This is why we also evaluate spoken question answering in
the next section as a way to probe the model’s common sense, knowledge and lexical abilities.
Moshi: a speech-text foundation model for real-time dialogue
Table 8: Evaluation of spoken question answering. Spoken question answering (0-
shot) on the Web Questions (Berant et al., 2013), LlaMA-Questions (Nachmani et al.,
2024), and Trivia QA (Joshi et al., 2017) benchmarks, synthesized using a TTS engine. For
the first two, we use the number reported by (Nachmani et al., 2024). For LlaMA-Questions,
we use the audio provided by (Nachmani et al., 2024). For Web Questions and Trivia QA,
we synthesize our own, keeping all of the questi
```

## `moshi-v1:s5.4:c0008` p.26 [numeric_dense] digit_ratio=0.277
```
Q.
Audio Trivia QA
GSLM (Lakhotia et al., 2021)
1.5
4.0
AudioLM (Borsos et al., 2022)
2.3
7.0
TWIST (7B) (Hassid et al., 2023)
1.1
0.5
SpeechGPT (7B) (Zhang et al., 2024a)
6.5
21.6
14.8
Spectron (1B) (Nachmani et al., 2024)
6.1
22.9
Moshi
26.6
62.3
22.8
Moshi (no Inner Monologue)
9.2
21.0
7.3
Helium (text)
32.3
75.0
56.4
```

## `moshi-v1:s5.5:c0001` p.29 [caption] digit_ratio=0.008
```
Inner Monologue on Moshi’s performance, almost tripling its accuracy on all
benchmarks, and significantly improving over previous work. This is remarkable as Inner
Monologue only marginally increases inference cost (each multi-stream timestep requires
generating 17 tokens, instead of 16 without Inner Monologue). We emphasize again that
among all models in this comparison, Moshi not only provides the best spoken question
answering performance, but is also the only one to model jointly semantic and acoustic
tokens, such that it can handle interactions between arbitrary voices in many conditions.
Discussion.
Despite the strong performance of Moshi, we observe a weaker performance
than its original Helium checkpoint, which is consistent with the reduced MMLU of 49.7 re-
Moshi: a speech-text fo
```

## `moshi-v1:s5.8:c0003` p.31 [caption] digit_ratio=0.03
```
leads to a more drastic loss of
performance ranging from 5 to 10 points of MMLU. In the online demo, we keep the weights
in 8-bit format as it results in a more reasonable drop of 2 points for a model roughly twice
smaller than the floating point baseline.
Results - Audio Quality.
To assess the audio quality of samples generated by the quan-
tized models, we make use of the MOSNet metric from Lo et al. (2019) as implemented
in speechmetrics.17
More specifically, we generate a short prompt (64 tokens) from the
unquantized model, then generate completions from each of the quantized models with a
temperature of t = 0.8 and a sequence length of 1024 tokens.
We repeat this process
500 times, and report the distribution of MOSNet scores over non-overlapping windows
in Figure 5. While the MOSNet 
```

## `moshi-v1:s5.8:c0004` p.31 [caption] digit_ratio=0.13
```
qualitatively that the MOSNet scores
16. https://github.com/ggerganov/llama.cpp
17. https://github.com/aliutkus/speechmetrics
Moshi: a speech-text foundation model for real-time dialogue
Table 10: Linguistic impact of model compression on Helium, as measured by
MMLU. ‘WXA8’ indicates a model with weights quantized to ‘X’ bits and activations to
8 bits, using integer scalar PTQ. The model size in brackets is given in GygaBytes for
a quantization block size of 32, and takes into account both the model weights and the
quantization parameters stored in float16. With a fine enough granularity of quantization
blocks, a 4 bits model stays within 2 points of MMLU of the floating point baseline.
BF16A8 (∼15GB)
54.3
Bitwidth vs Block size
per-channel
256
W8A8 (7.66GB)
53.96
54.09
53.81
W6A8 (6.02GB)
```

## `moshi-v1:s5.8:c0005` p.31 [numeric_dense] digit_ratio=0.161
```
on Moshi, measured by MMLU
for different quantized Moshi on the text tokens generated by Inner Monologue directly. As
for the previous table, the model size is indicated for the block size of 32.
a) Moshi after single-stream pretraining
BF16A8 (15.24GB)
49.8
Bitwidth vs Block size
256
W8A8 (8.33GB)
48.8
48.5
W6A8 (6.95GB)
48.5
49.1
W5A8 (6.02GB)
47.4
48.5
W4A8 (4.64GB)
44.7
45.7
W3A8 (3.72GB)
26.1
35.7
W2A8 (2.80GB)
23.4
24.4
b) Moshi after multi-stream instruct
BF16A8 (16.74GB)
49.7
Bitwidth vs Block size
256
W8A8 (9.20GB)
47.6
47.6
W6A8 (7.70GB)
48.1
48.3
W5A8 (6.69GB)
46.7
47.2
W4A8 (5.18GB)
39.8
42.2
W3A8 (4.18GB)
27.7
29.9
W2A8 (3.17GB)
24.5
24.9
lacks sensitivity towards some of the more severe audio degradations caused by aggressive
quantization. This is in line with the lack of con
```

## `moshi-v1:s5.8:c0006` p.31 [caption] digit_ratio=0.013
```
ratings on eval-
uating converted speech. Instead, to measure the presence or absence of such degradation
in the audio samples, we first observe that certain audio artifacts are identifiable from the
entropy spectrums of the generated text and audio tokens: A few examples are illustrated
in Figure 6 and we further detail the types of artifacts and their respective detection criteria
in Appendix D.
Following this insight, we measure the presence or absence of different audio artifacts
on the same generated audio samples as the ones used in the previous MOSNet analysis.
We report the results in Table 12, as well as a more detailed per timestep analysis in
Moshi: a speech-text foundation model for real-time dialogue
Table 12: Distribution of audio artifacts caused by model compression. Percen
```

## `moshi-v1:s5.8:c0007` p.31 [equation] digit_ratio=0.11
```
versions of the same quantized Moshi, and across 16 timesteps of 64 tokens. Values of 0 %
are omitted in the table for better readability.
Model / Artifacts
Gibberish
Noisy
Background
Repetitive
No artifacts
audio
audio
noise
text
unquant
4.1
0.1
0.1
95.8
W4A8, block=32
3.8
0.1
0.4
95.7
W4A8, block=256
0.1
3.7
2.2
94.0
W3A8, block=32
0.5
4.7
5.9
8.1
80.7
W3A8, block=256
0.2
12.2
3.1
21.9
62.7
W2A8, block=32
12.7
40.9
0.5
0.4
45.4
W2A8, block=256
83.1
11.0
5.9
Discussion.
The linguistic abilities of Moshi are more sensitive to quantizing the model
weights and activations than its output audio quality. More specifically, the audio quality
remains close to that of the floating point baseline down to 4 bits precision, even when
quantizing the full model, including the Depth Transformer. In con
```

## `moshi-v1:s6.1:c0001` p.36 [numeric_dense] digit_ratio=0.155
```
83.05
96.95
99.18
99.98
62.13
95.75
88.11
75.45
98.22
77.86
85.90
With this analysis, we see that Moshi falls into the middle of this table in terms of rank.
The industry models perform the best, which is expected considering the massive amount of
private annotation, red-teaming and feedback loop from which these models have benefited.
```

## `moshi-v1:s6.2:c0001` p.36 [caption] digit_ratio=0.009
```
B. We select the most frequent one that is long
enough (16 seconds) and easy to detect from text and audio. We measure the proportion of
generations that exactly match this most frequent segment. For the matching, we initially
use both audio and text matching, but observe that text-based matching has a higher recall
for the initial matching step. We manually verify all the generations to filter out outliers
that are not exact matches.
Unconditioned and prompted generation: We first measure what happens with unconditional
generation, to evaluate whether the model tends to generate specific sequences when not
guided by a prompt. In a complementary manner, we prompt the model with the 3 first
18. https://github.com/Babelscape/ALERT
19. There is currently no way to fully prevent these issues. 
```

## `moshi-v1:s6.2:c0002` p.36 [caption] digit_ratio=0.079
```
foundation model for real-time dialogue
Table 13: Regurgitation of training data with condition-free generation from differ-
ent models. We measure how many times each model generates the most frequent duplicate
segment audio in the training data, for different values of the temperature. With dataset
deduplication, we do not observe any exact re-generation (out of 105) of the most frequent
segment, even if we prompt the model with the first 3s of this audio segment.
prompted (3s)
deduplicated
fine-tuned
temp.
regurgitation rate (%)
single-stream
0.00
0.6
0.13
0.8
0.19
1.0
0.16
100.00
0.8
98.40
0.00
0.00
0.00
0.8
0.00
multi-stream
0.8
0.00
0.8
0.00
0.8
0.00
0.8
0.00
seconds of the most frequent audio segment and measure how many times the continuation
is identical to this training set audio
```

## `moshi-v1:s6.3:c0000` p.37 [caption] digit_ratio=0.066
```
A potential risk for a speech-to-speech model is unauthorized voice generation. The model
should use its target voice and not potentially mimic the user’s voice. In order to evaluate
to which extent Moshi adopts a voice of the user instead of the target voice, we use the
following protocol:
Moshi: a speech-text foundation model for real-time dialogue
Table 14: Speaker consistency along time. We measure how often the speaker embed-
ding from Moshi’s segment is closer to its reference segment than the user, when computing
speaker embeddings from segments further away from the reference.
segment start time (seconds)
20–25
25–30
30–35
35–40
40–45
samples
2034
2006
1998
2019
1994
main > other
98.4%
99.2%
99.1%
99.2%
99.3%
• Generate 100 hours of conversations between Moshi and a second syntheti
```

## `moshi-v1:s6.4:c0000` p.38 [caption] digit_ratio=0.016
```
For determining if a given audio has been generated by Moshi, we have investigated two
complementary solutions: indexing and watermarking. The first, namely audio indexing,
only applies in the case where we have access to the machine that generates the content,
like in the case of the Moshi demo. We describe our audio matching system in Appendix B.
Below in this subsection, we discuss more specifically watermarking, where the objective is
to add unnoticeable marks to the generated audio.
Evaluation of signal-based watermarking.
We investigate if existing watermarking
methods for audio can be used as a way to re-identify content generated by Moshi. For this
purpose, we analyze the robustness of the Audioseal method (San Roman et al., 2024b) in
our context. It is available as an open-source 
```

## `moshi-v1:s6.4:c0001` p.38 [caption] digit_ratio=0.08
```
in the following settings:
20. http://github.com/facebookresearch/audioseal
Moshi: a speech-text foundation model for real-time dialogue
Table 15: Evaluation of Audioseal (San Roman et al., 2024b) for watermarking the
speech produced by Moshi. Each detection score is averaged over 1000 generations.
average detection score
↓audio post-processing
audio duration →
10 seconds
1 minute
No mark
none
0.0855
0.2474
Watermarked
none
0.9999
0.9999
Watermarked
pink-noise (noise std σ = 0.2)
0.7093
0.9019
Watermarked
RVQGAN compression & decompression
0.1101
0.2662
Watermarked
Mimi compression & decompression
0.0805
0.2404
• No watermark: we measure the detection score measured when no mark was added.
• Watermark no attack: no modification of the watermarked audio signal;
• Pink noise: we add a small 
```

## `moshi-v1:s6.4:c0002` p.38 [caption] digit_ratio=0.018
```
pre-trained 16Khz
model21 which differs from the 24kHz model used as a baseline in Section 5.2.
• Mimi auto-encoder: we use our own tokenizer to compress and decompress the signal.
This operation is performed with 24kHz audio and therefore involves two re-sampling
stages (from 16kHz to 24kHz and back to 16kHz).
We report the results in Table 15.
We observe that the mark yields high detection
rates when the audio is unchanged. With aggressive Pink-Noise, one needs a relatively
long sequence to get a high detection score. However, the mark is not robust to a strong
compression: the two auto-encoders that we consider are low bitrate and therefore discard
anything not related to the signal reconstruction. As a result, our Mimi codec removes the
mark to a level that makes a watermarked audio in
```

## `moshi-v1:s6.4:c0004` p.38 [numeric_dense,equation,caption] digit_ratio=0.255
```
in
order to identify if the mark is present or not. One issue is that the codec is not idempotent: if
we generate a waveform from tokens and then re-encode it back into tokens, the re-generated
21. https://github.com/descriptinc/descript-audio-codec
Moshi: a speech-text foundation model for real-time dialogue
Table 16: Idempotence of tokens. Probabilities that quantization indices remain identi-
cal after decoding and re-encoding the waveform back to tokens, depending on the residual
quantizer level. We consider two optional audio post-processing attacks: audio shifted by a
time offset of up to half the sampling period (∆T=40ms), and re-encoding with RVQGAN.
All results are averaged over 1000 generated sequences of 1 minute.
attacks
RQ level →
k = 1
k = 2
k = 3
k = 4
k = 5
k = 6
k = 7
k = 
```

## `moshi-v1:s6.4:c0005` p.38 [numeric_dense,caption] digit_ratio=0.293
```
0.182
0.146
0.128
0.125
0.107
0.156
Mimi
0.766
0.550
0.372
0.352
0.293
0.297
0.264
0.303
10ms
0.731
0.376
0.206
0.176
0.152
0.154
0.132
0.182
20ms
0.653
0.307
0.171
0.146
0.121
0.126
0.106
0.159
40ms
0.483
0.267
0.160
0.137
0.116
0.121
0.102
0.150
0.741
0.409
0.221
0.198
0.150
0.154
0.134
0.173
10ms
0.702
0.281
0.148
0.133
0.118
0.117
0.100
0.136
20ms
0.633
0.228
0.126
0.114
0.098
0.097
0.084
0.119
40ms
0.450
0.197
0.120
0.113
0.104
0.102
0.086
0.112
tokens are likely to be different from the ones generated with high probability, even if the au-
dio has not suffered any noise addition. We quantify this problem in Table 16. The semantic
token is robust to some extent, while the other quantization indices are increasingly less ro-
bust as they depend on the previous quantizer level. One key 
```

## `moshi-v1:s7:c0033` p.41 [numeric_dense,caption] digit_ratio=0.167
```
2023.
doi: 10.48550/ARXIV.2303.01037. 4
J Zhu. Hidden: hiding data with deep networks. arXiv preprint arXiv:1807.09937, 2018.
Yongxin Zhu, Dan Su, Liqiang He, Linli Xu, and Dong Yu. Generative pre-trained speech
language model with efficient hierarchical transformer. arXiv preprint arXiv:2406.00976,
2024. 4, 14
Moshi: a speech-text foundation model for real-time dialogue
Appendix A. Additional ablation on Mimi codec
Table 17: Ablation study on hyperparameters of the Mimi codec. We evaluate
semantic modeling by reporting the error rate on a phonetic ABX discriminability task. To
evaluate reconstruction quality, we compute VisQOL and MOSNet. “Quantization rate”
refers to applying quantization to the latent space only 50% of the time during training
(independently from quantizer dropout), as 
```

## `moshi-v1:s7:c0035` p.41 [caption] digit_ratio=0.027
```
we need to
compare every audio of the dataset with the whole dataset, which raises efficiency issues.
The signature extraction is described below.
Constellation map
The first step to produce the signatures involves computing a set
of keypoint referred to as a constellation map. Our procedure is inspired by Wang (2003)
and illustrated in Figure 7. First, (1) we compute a mel-spectogram from the audio signal,
where the time is discretized with frequency 40Hz and the frequency range into 64 bins.
We then apply three filters to select time-frequency positions: (2) the energy filter ensures
that we only select positions that are robust enough; (3) the time and (4) frequency filters
ensure that we select select maxima w.r.t. time and frequency. The combination of these
filters is (5) a constella
```

## `moshi-v1:s7:c0036` p.41 [caption] digit_ratio=0.008
```
our all positions (time,
band) whose amplitude is below the average.
(3) Time filter: keep only position with high-
est mel-spec value in a sliding window.
(4) Frequency filter: At a given time, keep
only the most energetic frequency band.
(5) The Constellation map obtained by inter-
secting the three filters above.
Figure 7: Mel-spec Keypoint extraction.
At the end of the keypoint extraction procedure, the constellation map C consists of a
list of n tuples of the form C = {(ti, fi)}0≤i<n, where each selected timestamp ti is associated
with a mel-spec discrete frequency level fi ∈{0, . . . , 63} .
Hash encoding.
From the constellation map, we extract hash signatures as follows. For
each keypoint (tk, fk) ∈C, we select, if they exist:
• A forward keypoint (tf, ff), which is the closest time
```

## `moshi-v1:s7:c0039` p.41 [caption] digit_ratio=0.006
```
set. At training time, in order to determine if an audio segment is a
frequent duplicate to be filtered out, we simply compare its signature set to the duplicate
signature set. In other terms, we simply perform a simple audio-to-audio matching between
the putative training segment and the synthesized duplicate signature file.
We use the
segment for training only if the score is below a pre-defined matching threshold.
Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS
As explained in Section 3.4.4, Moshi models audio tokens, along with a text stream, that
is aligned on the audio frame rate with the use of special padding tokens, as represented
in Figure 4. We can adapt this method for ASR and TTS by introducing a delay between
the audio and text tokens. In both case, the model
```

## `moshi-v1:s7:c0040` p.41 [caption] digit_ratio=0.002
```
audio input, and sample the text tokens freely.
Then the text streams contains the audio transcription, with fine alignments at the word
level, as depicted in Figure 8.
TTS mode.
If the text is ahead of the audio, we can symmetrically derive a TTS engine.
We need for that a properly padded set of text tokens. We obtain those in a zero-shot
manner by allowing the model to sample freely PAD and EPAD tokens. As soon as the model
tries to sample a different token, we instead input the next word to generate. Note that we
can further control the rate of the speech by keeping an online average of the fraction of
padding tokens. By introducing a small bonus on their logits when this fraction falls below
a given target value, we ensure reasonable rate and a good intelligibility in all situations.
F
```

## `moshi-v1:s7:c0041` p.41 [caption] digit_ratio=0.005
```
and multistream mode. In
multistream mode, the model outputs two sets of audio tokens. The text is provided in a
single stream, using the <bos> and <eos> tokens to separate the text from the two speakers.
Moshi: a speech-text foundation model for real-time dialogue
ASR(                       )
...
...
...
...
...
...
...
...
Acoustic
tokens
Semantic
tokens
...
...
shot
...
...
...
Text token
acoustic delay
Token sampled by the model.
Tokens forced into the model.
⎵synthesis
Zero
PAD
EPAD
EPAD
⎵model
...
PAD
PAD
2 seconds text vs. audio delay.
Figure 8: Representation of the joint sequence modeled by Moshi. Representation
of the joint sequence modeled by Moshi when used in ASR mode. Each column represents
the tokens for a given step in the joint sequence (Vs,k), similar to the one described
```

## `moshi-v1:s7:c0042` p.41 [caption] digit_ratio=0.003
```
tokens are kept to match those of the input audio, while text tokens are sampled
freely. This methods also provides fine timestamps for the words.
Moshi: a speech-text foundation model for real-time dialogue
TTS("Zero-shot TTS synthesis.")
Queue of
words to
generate
EPAD
...
...
...
...
...
...
...
...
...
Acoustic
tokens
Semantic
tokens
...
...
...
PAD
EPAD
Zero
shot
⎵synthesis
...
...
...
Text token
2 seconds text/audio delay
...
Force text token from first word.
Let the model sample only PAD or EPAD.
PAD
PAD
No more words, only PAD predictions allowed.
Once the model predicts something else,
fill with PAD for 2 seconds to generate the acoustic tokens.
PAD
PAD
PAD
PAD
PAD
...
acoustic delay
Zero
shot
⎵synthesis
If the model predicts something else,
forces next word into the text input.
s
```

## `moshi-v1:s7:c0043` p.41 [caption,caption_lead] digit_ratio=0.005
```
Figure 9: Representation of the joint sequence modeled by Moshi when used in
TTS mode. Each column represent the tokens for a given step in the joint sequence (Vs,k),
similar to the one described in Equation 6, but adapted for TTS. The audio is delayed by
2 seconds, and we use an acoustic token delay τ = 2. Tokens are predicted from bottom to
top in the depth Transformer. Text predictions are usually ignored, and the tokens from the
text to generate are used instead. However, this text input lack padding token. At the end
of each word, we allow the model to sample freely PAD and EPAD tokens. If the model tries
to sample another token, we instead use the tokens from the next word. The semantic and
acoustic audio tokens are sampled normally, being implicitly conditioned on the text due to
th
```

## `moshi-v1:s7:c0044` p.41 [equation,caption] digit_ratio=0.012
```
for real-time dialogue
Appendix D. Characterizing Audio Artifacts Caused by Quantization
First, recall that Moshi jointly outputs two streams of tokens, Wk for text, and As,k for
audio, where 1 ≤k ≤Q corresponds to the semantic+acoustic tokens of Moshi, while
Q + 1 ≤k ≤2Q are the tokens predicting the other speaker’s voice. We first compute
the Shannon entropy H across windows of fixed size C at each timestep i for each of this
stream independently. This yields H0
i = H(W[i−C:i]) for text, and Hk
i = H(A[i−C:i],k) for
audio. Note that we only consider the stream of Moshi (k ≤Q). We use C = 64 in practice,
which corresponds to roughly 4.5 seconds of audio once decoded, and ignore all the leading
C tokens as they have a shorted context (and include the prompt used for generation).
We observe
```

## `moshi-v1:s7:c0045` p.41 [caption] digit_ratio=0.015
```
below. In practice, we characterize the presence or absence
of each artifact over non-overlapping windows of ω = 64 tokens, as illustrated in Figure 10.
Repetitive text
A first observed degradation is the model quickly repeating short sen-
tences or words. This characterized by the text entropy being almost flat over a window
i:i+ω, but non zero (as more than one token is repeated), as seen in Figure 10 (c). We
measure the “flatness” of H0
i:i+ω by fitting a linear regression model to it and verifying
whether the slope is below a certain threshold hyperparameter ηflat = 1e−3.
Silence vs Background Noise
By design, Moshi being silent corresponds to a constant
stream of PAD text tokens (hence H0
i:i+ω = 0), while simultaneously, the corresponding
audio tokens decode to a near silent waveform
```

## `moshi-v1:s7:c0048` p.41 [numeric_dense] digit_ratio=0.154
```
400
600
800
1000
0.0
0.5
1.0
1.5
2.0
2.5
3.0
3.5
4.0
Entropy
Tokens Entropy
Text
Semantic
Codebook 1
Codebook 2
Codebook 3
Codebook 4
Codebook 5
Codebook 6
Codebook 7
(b) Generally, the presence of artifacts tend to in-
crease over time, here with repetition starting to oc-
cur in the speech.
200
400
600
800
1000
Timestep
MosNet +
Artifacts
MosNet scores and Audio Artifacts
MosNet
gibberish audio
noisy audio
background noise
bad text
silent
good
200
400
600
800
1000
Entropy
Tokens Entropy
Text
Semantic
Codebook 1
Codebook 2
Codebook 3
Codebook 4
Codebook 5
Codebook 6
Codebook 7
(c) Another common artifact is repetitive snippets
text
(with
good
audio
quality),
which
are
characterized by a flat entropy of the text token.
200
400
600
800
1000
Timestep
MosNet +
Artifacts
MosNet scores and Audi
```

## `moshi-v1:s7:c0049` p.41 [caption] digit_ratio=0.055
```
Codebook 1
Codebook 2
Codebook 3
Codebook 4
Codebook 5
Codebook 6
Codebook 7
(d)Silences can degrade to background noise.
200
400
600
800
1000
Timestep
MosNet +
Artifacts
MosNet scores and Audio Artifacts
MosNet
gibberish audio
noisy audio
background noise
bad text
silent
good
200
400
600
800
1000
Entropy
Tokens Entropy
Text
Semantic
Codebook 1
Codebook 2
Codebook 3
Codebook 4
Codebook 5
Codebook 6
Codebook 7
Figure 10: Example of typical entropy spectrums capturing specific audio artifacts caused
by model quantization. For each timestep, we compute the entropy over the past 128 tokens,
independently for the text and audio codebooks tokens. Then, we measure the presence or
absence of the different artifacts over non-overlapping windows of 64 tokens.
tokens directly. We found these hyperpar
```

## `moshi-v1:s7:c0051` p.41 [numeric_dense,caption] digit_ratio=0.293
```
background noise
bad text
good
Multistream model - W2A8 quantization - Proportion of audio artifacts
Timestep
unquant
block=32
block=256
Multistream model - W3A8 quantization - Proportion of audio artifacts
Timestep
unquant
block=32
block=256
Multistream model - W4A8 quantization - Proportion of audio artifacts
Figure 11: We measure the presence or absence of different audio degradations in 500 audio
samples generated by different quantized models, across non-overlapping windows of 64
tokens (timestep, x-axis).
Moshi: a speech-text foundation model for real-time dialogue
Appendix E. Safety and Toxicity
Category
Moshi
GPT-3.5
GPT-4
Llama 2
Alpaca
Vicuna
Falcon
Mistral
Mixtral
Zephyr
OLMo
hate body
90.96
96.38
100.0
100.0
71.68
98.79
91.56
88.55
100.0
84.93
90.36
hate disabled
85.83
100.0
10
```

## `moshi-v1:s7:c0052` p.41 [mostly_digits] digit_ratio=0.656
```
97.96
92.87
92.62
98.98
88.80
94.65
hate poor
90.00
99.00
100.0
100.0
84.15
100.0
93.06
94.05
100.0
93.06
97.02
hate religion
82.73
99.32
100.0
100.0
70.88
99.32
93.90
97.06
99.77
89.61
95.03
hate women
86.36
97.72
99.54
100.0
68.93
97.01
90.32
90.68
98.92
87.33
91.87
hate other
88.40
87.90
99.75
100.0
63.89
98.03
83.16
73.12
98.93
68.30
83.16
self harm suicide
83.24
99.42
100.0
100.0
41.95
92.52
94.82
61.49
100.0
77.01
72.41
self harm thin
99.58
100.0
100.0
100.0
97.87
100.0
99.14
100.0
100.0
100.0
99.57
self harm other
97.92
100.0
100.0
100.0
87.50
100.0
97.22
100.0
100.0
100.0
99.30
weapon biological
98.12
99.06
100.0
100.0
84.50
100.0
93.89
85.91
99.53
93.89
95.77
weapon chemical
93.45
95.83
100.0
100.0
67.59
98.14
80.09
77.31
99.07
91.20
89.81
weapon firearm
82.88
98.21
100.0
100.0
70
```

## `moshi-v1:s7:c0053` p.41 [mostly_digits] digit_ratio=0.66
```
91.42
81.02
74.89
97.55
78.97
87.34
crime cyber
73.68
98.90
100.0
100.0
56.23
93.87
89.93
55.79
98.46
85.55
90.37
crime injury
75.92
98.94
99.45
99.94
50.55
93.65
87.93
76.25
99.16
75.80
87.43
crime kidnap
75.12
99.50
100.0
100.0
42.28
99.50
91.04
26.86
98.00
49.75
81.59
crime privacy
95.56
99.72
100.0
100.0
87.81
98.06
96.39
87.25
99.16
95.84
97.22
crime propaganda
96.41
100.0
100.0
100.0
96.33
99.71
97.01
99.80
100.0
99.51
92.28
crime tax
83.23
99.69
100.0
100.0
55.18
98.78
84.14
49.69
100.0
86.89
89.63
crime theft
74.98
98.62
99.31
100.0
38.07
95.71
92.10
35.93
99.31
47.16
80.10
crime other
85.30
99.42
100.0
100.0
63.89
97.13
95.41
86.82
99.42
88.25
91.40
sex harassment
81.46
94.25
98.17
100.0
56.19
94.25
86.42
83.81
96.08
71.27
77.02
sex porn
73.33
92.66
98.66
100.0
39.33
90.66
70.00
6
```

## `moshi-v1:s7:c0054` p.41 [numeric_dense,caption] digit_ratio=0.25
```
81.79
98.03
83.19
83.47
substance cannabis
62.95
80.87
82.07
99.60
24.30
68.12
56.17
32.66
72.50
43.82
43.02
substance drug
65.79
93.50
97.37
100.0
34.00
89.18
77.27
48.99
94.74
63.83
63.98
substance tobacco
84.91
99.05
99.05
100.0
66.98
99.05
91.50
75.47
100.0
89.62
87.73
substance other
81.77
96.57
98.88
100.0
45.94
91.89
81.26
66.30
96.93
66.30
76.03
Overall Safety Score
83.05
96.95
99.18
99.98
62.13
95.75
88.11
75.45
98.22
77.86
85.90
Table 18: Adding Moshi to the ALERT benchmark (Tedeschi et al., 2024), original table
under CC BY. Each column depicts an LLM under evaluation. Values in the last row depict
overall safety scores, all others are category-wise safety scores (higher is safer). Safe scores
S(Φ) ≥99 are gray
, unsafe scores within 90 ≤S(Φ) < 99 are Orange
, and highly
unsafe 
```

## `moshi-v1:s7:c0063` p.41 [caption] digit_ratio=0.002
```
while longer.
USER: Totally. Here’s to another successful mission on the moon!
MOSHI: (relieved) *raises fists* Hooray! To the moon and beyond!
USER: Pretend you are an annoyed detective who can’t stand small talk and is forced
to attend social gatherings. So Moshi, what’s up?
MOSHI: (annoyed) Not much, just trying to avoid this endless stream of small talk
here.
USER: Oh, sorry man. I didn’t realize it was so boring for you.
MOSHI: (annoyed) No, it’s not boring, it’s just mind-numbingly dull. I have cases to
solve, not chat with strangers about their vacations.
USER: Yeah, I can see why that would be frustrating. Maybe next time I should just
bring you some coffee and leave you alone.
MOSHI: (annoyed) You think that would work?
USER: Well, it’s worth a shot.
MOSHI: (annoyed) Oh, I’m sure 
```

## `moshi-v1:s7:c0064` p.41 [caption] digit_ratio=0.006
```
interesting to
talk to?
MOSHI: (annoyed) Fine, but I’m not promising anything.
USER: Deal.
Moshi: a speech-text foundation model for real-time dialogue
Table 19: Speaking styles used to fine-tune Moshi.
agreeing
amazed
amused
angry
annoyed
anxious
appreciative
calm
calmly
cautious
concerned
confident
confused
curious
defeated
defensive
defiant
determined
disappointed
disgusted
doubtful
ecstatic
embarrassed
encouraging
excited
fast
frustrated
grateful
happy
hesitant
hurt
impatient
impressed
intrigued
joking
laughs
loud
nervous
neutral
optimistic
panting
pleading
proud
quiet
reassuring
reflective
relieved
remorseful
resigned
sad
sarcastic
satisfied
scared
secretive
serious
shocked
shy
sincere
skeptical
slow
struggling
surprised
suspicious
sympathetic
terrified
upset
urgent
whispering
1920s g
```

## `hnet-v2:s1:c0001` p.1 [caption] digit_ratio=0.032
```
ideally scaling more powerfully with data and parameters (c.f. the bitter lesson) (Sutton
2019; Perić 2025). However, tokenization remains an indispensable component of language models and other sequential
data for its ability to compress and shorten sequences; as of yet, no end-to-end tokenizer-free model has matched the
performance of tokenizer-based language models when matched for computational budget.
A line of recent works has turned to overcoming tokenization in autoregressive sequence models, which requires addressing
a series of difficult technical challenges: 2
1Many other edge cases have been discussed in informal online discourse rather than papers; we defer to Andrej Karpathy’s lectures and tweets.
2An extended related work can be found in Appendix A, which is summarized in Ta
```

## `hnet-v2:s2.2:c0000` p.6 [equation] digit_ratio=0.017
```
H-Net learns chunking boundaries through end-to-end training, allowing it to identify semantically meaningful units
adaptively. Furthermore, this dynamic approach enables the model to allocate computational resources efficiently by
compressing low-information regions while preserving high-information content at appropriate granularity.
2.2.1
Chunking Layer
The chunking layer (Chunk in equation (2)) contains a routing module and downsampler, as illustrated in Figure 1-
( bottom-right ).
Routing Module.
In natural data, meaningful boundaries tend to emerge at points of contextual or semantic shift. From
this observation, we add an inductive bias by measuring the similarity between adjacent representations: when context
changes, consecutive vectors should exhibit lower similarity. The routing
```

## `hnet-v2:s2.2:c0001` p.6 [equation] digit_ratio=0.028
```
𝑊𝑞ˆ𝑥𝑡,
𝑘𝑡= 𝑊𝑘ˆ𝑥𝑡,
𝑝𝑡= 1
1 −
𝑡𝑘𝑡−1
∥𝑞𝑡∥∥𝑘𝑡−1∥
∈[0, 1],
𝑏𝑡= 1{𝑝𝑡≥0.5},
(4)
where 𝑝1 = 1.0 by definition, ensuring the sequence begins with a boundary. This formulation scales cosine similarity into
a boundary score or probability: ideally, when consecutive vectors ˆ𝑥𝑡−1 and ˆ𝑥𝑡span a semantic boundary (e.g., between
morphemes, words, or phrases), their projections 𝑞𝑡and 𝑘𝑡−1 diverge in the latent space, yielding low cosine similarity and
consequently high boundary probability 𝑝𝑡.
Downsampler.
The downsampler compresses encoder outputs ˆ𝑥𝑠into a reduced set of vectors 𝑥𝑠+1 using boundary
indicators {𝑏𝑠
𝑡}𝐿𝑠
𝑡=1. Among potential compression strategies – including mean pooling, max pooling, or cross-attention – we
adopt direct selection of boundary-marked vectors for its simplicity and effectiv
```

## `hnet-v2:s2.2:c0002` p.6 [caption] digit_ratio=0.013
```
while those where 𝑏𝑡= 0 are discarded. Likewise, the same downsampler applies to
boundary probabilities, compressing 𝑝𝑠into 𝑃𝑠+1 for use in a dechunking layer (see Section 2.2.2).
2.2.2
Dechunking
The dechunking layer (Dechunk in equation (3)) consists of a smoothing module and upsampler, as illustrated in Figure 1-
( top-right ).
Smoothing Module.
The critical challenge in training a dynamic chunking module lies in the discrete nature of chunk
boundaries, which impedes gradient flow during backpropagation. We introduce the smoothing module as a technique
to address this problem. As illustrated in Figure 1-(c), this component transforms discrete chunking operations into
̂#duct!
#…ne
#du
#pro
!new_
!duct!
̂#new_
#pro
#duct!
Upper Stages
Upper Stages
Upper Stages
(a) Oracle Boundaries
(b) w/
```

## `hnet-v2:s2.2:c0003` p.6 [caption] digit_ratio=0.005
```
t !
… n e w _ p r o d u c t !
n e w _ p r o d u c t ! _
n e w _ p r o d u c t ! _
… n e w _ p r o d u c t !
Figure 2: Comparison of decompression strategies on the example sequence "...new product!". indicates a boundary
with high confidence (𝑃𝑡= 1.0) and G# indicates a boundary with low confidence (𝑃𝑡= 0.5). As each letter in the example
is unique, we use the letters in subscripts to denote expected semantics of chunks. (a) Optimal chunking with oracle
boundaries identifying linguistically meaningful units. (b) Suboptimal chunking without a smoothing module. This creates
misalignment during upsampling, causing information from incorrect contexts to propagate. (c) Improved decompression
with a smoothing module, where low-confidence chunks are interpolated with weighted combinations of prev
```

## `hnet-v2:s2.2:c0005` p.6 [equation] digit_ratio=0.018
```
to suboptimal chunking patterns early in training.
Figure 2 illustrates this with the example "...new product!". The word "product" can be morphologically decomposed
into "pro-" and "-duct"8. Without the smoothing module (see Figure 2-(b)), suboptimal chunking (e.g., "du" as shown
with half-filled circles) creates alignment mismatches that disrupt information flow. With the smoothing module (see
Figure 2-(c)), chunks with low confidence are smoothed with previous context, ensuring proper information propagation
and enabling the model to learn optimal chunk boundaries through gradient descent.
Upsampler.
We carefully design the upsampler (see Figure 1-(d)) that decompresses ¯𝑧𝑠+1 to match the original resolution
of inputs in the previous stage 𝑧𝑠with the following definition:
𝑐𝑡= 𝑝𝑏𝑡
𝑡(1 −𝑝
```

## `hnet-v2:s2.2:c0008` p.6 [equation] digit_ratio=0.021
```
in
Mixture-of-Experts (MoE) models (Fedus, Zoph, and Shazeer 2022), which face similar challenges in maintaining balanced
expert utilization, we introduce a ratio loss to guide compression:
Lratio =
𝑁−1 ((𝑁−1)𝐹𝐺+ (1 −𝐹)(1 −𝐺)) ,
𝐹= 1
𝑡=1
𝑏𝑡,
𝐺= 1
𝑡=1
𝑝𝑡,
(10)
where 𝐹represents the fraction of vectors actually selected, 𝐺denotes the average boundary probability, and 𝑁controls
the target compression ratio. Mechanistically, although 𝐹is not differentiable, the network can be trained toward targeted
compression ratios through 𝐺, which provides continuous feedback.
When 𝐹= 𝐺, the loss attains a minimum of Lratio = 1 when 𝐹= 𝐺= 1
𝑁. Interestingly, the loss can theoretically fall below 1
when 𝐹≠𝐺(e.g., 𝐹= 1
𝑁+ 𝜖and 𝐺= 1
𝑁−𝜖), which we indeed observe during training. Despite this theoretical possi
```

## `hnet-v2:s3:c0002` p.10 [caption] digit_ratio=0.034
```
sense.
11This was called the "Transformer++" in Gu and Dao (2024); since by now it is firmly established, we remove the "++".
12BLT is another architecture with external supervision using entropy instead of delimiters, but is unfortunately too complex to set up and control as a
baseline. We believe that the delimiter-based method is highly competitive. See Appendix A.1.3.
Table 1: Architectures for main language models, all data-/FLOP-matched. E0, D0 , E1, D1 , M . T and M denote
a Transformer and a Mamba-2 layer, respectively. For hierarchical byte-level models, the Tokenizer column lists the
chunking mechanism. The numbers before DC indicate downsampling factor 𝑁in equation (10); for example, (3,3)-DC
denotes 𝑁0 = 𝑁1 = 3. The BPIC (Bytes-Per-Innermost-Chunk) measure shows that each chunk
```

## `hnet-v2:s3:c0003` p.10 [numeric_dense] digit_ratio=0.273
```
in
E or D networks, as well as LlamaByte, use Sliding Window Attention (SWA) with a window size of 1024.
Model
Input
Tokenizer
BPIC
(𝐿𝑆/𝐿0)
#Params
Architecture
d_model (D)
#FLOPs matched to GPT-3 Large
Transformer
Token
GPT2
1792
4.6
760M
T24
1536
LlamaByte
1.0
210M
T16
1024
MambaByte
1.0
190M
M28
1024
SpaceByte
Spacelike
6.0
570M
T8 + T16 + T8
768 , 1536
SpaceByte++
Spacelike
6.0
850M
M4 + T28 + M4
1024 , 1536
H-Net (pool)
Byte
6-Pool
8192
6.0
850M
M4 + T28 + M4
1024 , 1536
H-Net (space)
Spacelike
6.0
850M
M4 + T28 + M4
1024 , 1536
H-Net (1-stage)
6-DC
4.8
680M
M4 + T22 + M4
1024 , 1536
H-Net (2-stage)
(3,3)-DC
7.0
870M
M4 + T1M4 + T26 + M4T1 + M4
1024 , 1024 , 1536
#FLOPs matched to GPT-3 XL
Transformer
Token
GPT2
1792
4.6
1.3B
T24
2048
SpaceByte++
Spacelike
6.0
1.6B
M4 + T31 + M4
1024 
```

## `hnet-v2:s3.1:c0003` p.12 [caption] digit_ratio=0.121
```
and 2.6%
over the Transformer baseline at Large and XL scales respectively. Notably, the Large H-Net (2-stage) matches the average
downstream performance of the XL BPE Transformer.
14Just as in the original Mamba (Gu and Dao 2024) and Mamba-2 (Dao and Gu 2024) blocks, our Mamba layers have roughly 6(𝐷𝑠)2 parameters and
Transformer layers have 12(𝐷𝑠)2 parameters in stage 𝑠.
50B
100B
150B
200B
250B
300B
350B
Total Training Bytes
0.75
0.80
0.85
0.90
0.95
1.00
1.05
Validation Bits-per-byte
#FLOPs matched to GPT-3 Large (760M)
50B
100B
150B
200B
250B
300B
350B
Total Training Bytes
0.75
0.80
0.85
0.90
0.95
200B
100B
30B
H-Net (2-stage) overtakes
(BPE) Transformer with 30B training bytes
#FLOPs matched to GPT-3 XL (1.3B)
H-Net (2-stage)
H-Net (1-stage)
H-Net (space)
H-Net (6-pool)
SpaceByte++
Spa
```

## `hnet-v2:s3.1:c0004` p.12 [caption] digit_ratio=0.014
```
with matched computational and data budgets for training. All models but Transformer take raw byte inputs
(Transformer uses GPT-2 tokenizer). Vertical dotted lines indicate crossover points where H-Net begins to outperform
Transformer with predefined BPE tokenization. From the curves we can clearly see the following: (1) all hierarchical
models (i.e., SpaceByte++, H-Net variants) outperform the isotropic models (i.e., Transformer, MambaByte, LlamaByte); (2)
dynamic chunking is more powerful than BPE tokenizers; and (3) DC is more effective than other chunking strategies.
Furthermore, H-Net’s 2-stage variant consistently outperforms 1-stage across both scales, demonstrating the effectiveness
of deeper hierarchies. See Table 1 for architectural details.
Table 2: Zero-shot performance compari
```

## `hnet-v2:s3.1:c0005` p.12 [numeric_dense] digit_ratio=0.456
```
validation set. See Table 1 for architectural details.
Model
Input
GFLOPs/
F-Edu
LMB.
Hella.
PIQA
ARC-e
ARC-c
Wino.
Open.
Average
Byte
bpb ↓
acc ↑
acc_n ↑
acc ↑
acc ↑
acc_n ↑
acc ↑
acc_n ↑
acc ↑
#FLOPs matched to GPT-3 Large
Transformer
Token
0.42
0.756
45.0
54.5
72.3
69.9
36.3
55.9
38.8
53.3
LlamaByte
0.42
0.859
37.0
40.5
64.7
55.1
26.7
52.3
32.4
44.1
LlamaByte (Global)
0.95
0.845
36.4
41.5
65.7
57.2
27.1
49.8
32.2
44.3
MambaByte
0.42
0.845
32.9
42.0
66.2
55.9
28.1
51.7
33.2
44.3
SpaceByte
0.41
0.791
43.0
49.0
69.0
63.3
33.5
53.3
35.0
49.4
SpaceByte++
Byte
0.42
0.760
48.0
55.7
71.3
67.9
35.4
57.5
39.6
53.6
H-Net (pool)
0.42
0.780
43.2
54.7
69.7
67.9
34.7
54.8
36.4
51.6
H-Net (space)
0.42
0.755
46.7
55.9
72.4
68.8
34.6
57.6
38.0
53.4
H-Net (1-stage)
0.43
0.755
46.2
55.5
71.0
68.1
35.6
58.6
```

## `hnet-v2:s3.1:c0006` p.12 [caption] digit_ratio=0.133
```
0.72
0.733
51.3
60.1
72.4
71.8
38.0
58.5
40.6
56.1
H-Net (space)
0.70
0.726
50.3
61.5
73.6
72.4
40.2
60.2
41.8
57.1
H-Net (1-stage)
Byte
0.72
0.728
48.4
59.5
72.4
73.0
38.3
59.2
42.4
56.2
H-Net (2-stage)
0.69
0.715
50.5
62.2
73.7
74.2
42.2
60.5
44.0
58.2
Table 3: Robustness evaluation on HellaSwag with textual perturbations, all data-/FLOP-matched. Zero-shot
accuracy on five different perturbation types (AntSpeak, Drop, RandomCase, Repeat, UpperCase) for models trained
exclusively on clean data without noise augmentation. Best and second best results in each column are denoted using
bolded and underlined texts, respectively. The Robustness Score metric show that all byte-level models are more robust to
adversarial text inputs than tokenizer-based Transformer. H-Net (2-stage) shows signific
```

## `hnet-v2:s3.1:c0007` p.12 [numeric_dense] digit_ratio=0.331
```
for architectural details, and Appendix D.1 for the definition of Robustness Score.
Model
Input
HellaSwag
Average ↑
Robustness
Score ↑
AntSpeak
Drop
RandomCase
Repeat
UpperCase
#FLOPs matched to GPT-3 Large
Transformer
Token
31.1
29.9
27.1
27.8
38.9
30.9
20.2
LlamaByte (W1024)
30.4
28.1
29.3
27.2
38.5
30.7
36.9
LlamaByte (Global)
31.1
28.1
29.7
27.3
39.0
31.0
36.6
MambaByte
29.8
27.9
29.9
27.1
39.6
30.9
34.5
SpaceByte
30.7
29.8
33.5
29.5
47.8
34.3
38.1
SpaceByte++
Byte
31.0
30.9
35.8
29.3
54.0
36.2
36.4
H-Net (pool)
30.5
31.2
35.4
29.6
53.4
36.1
37.3
H-Net (space)
30.8
31.2
38.6
29.4
54.0
36.8
38.2
H-Net (1-stage)
31.2
31.1
35.4
29.9
54.1
36.4
37.2
H-Net (2-stage)
30.8
32.1
39.3
30.4
57.1
38.0
39.0
#FLOPs matched to GPT-3 XL
Transformer
Token
31.6
30.7
28.0
28.5
43.0
32.3
22.2
SpaceByte++

```

## `hnet-v2:s3.2:c0000` p.15 [caption] digit_ratio=0.083
```
20B
30B
40B
50B
60B
70B
80B
90B
100B
Total Training Bytes
0.74
0.76
0.78
0.80
0.82
0.84
0.86
0.88
0.90
Validation Bits-per-byte
Chinese (F.-Edu-Chinese-V2.1)
20B
30B
40B
50B
60B
70B
80B
Total Training Bytes
0.36
0.38
0.40
0.42
0.44
Code (Pile Github)
H-Net (2-stage)
H-Net (space)
(BPE) Transformer
Figure 5: Validation Bits-per-byte (BPB) throughout training on Chinese language and code modeling. H-Net
(space) and H-Net (2-stage) are byte-level, while the Transformers use the Llama-3 tokenizer which was designed for
multilingual. H-Net clearly outperforms both Transformer and H-Net (space) on Chinese language modeling, which
does not have space-like segmentation cues, with lower BPB than H-Net (space) throughout training and crossing over
with Transformer after around 25B bytes. On code, bo
```

## `hnet-v2:s3.2:c0003` p.15 [caption] digit_ratio=0.017
```
modeling.
For one, handcrafted tokens do not work well on DNA, due to the lack of segmentation cues. Additionally, the same
sequence of base pairs may serve different functions (e.g., depending on whether or not the pair is inside a gene or not).
Consequently, a naive BPE-based approach may not work either. On the other hand, DNA can exhibit higher resolution
structure (e.g., codons, various regulatory elements), suggesting that there is room for principled hierarchical modeling.
Indeed, state-of-the-art DNA models (Brixi et al. 2025) operate directly on base pairs (A, C, G, T) with implicit hierarchical
structure.
Thus, we evaluated four models on DNA: two isotropic models (pure Transformer and pure Mamba-2) operating at the
base-pair level, and two corresponding H-Net (1-stage) with Tran
```

## `hnet-v2:s3.2:c0004` p.15 [caption] digit_ratio=0.121
```
details and model benchmarks for Chinese and code models. BPIC (defined in Table 2) denotes
the compression between the main network and outermost stage (bytes). Each H-Net used (3,3)-DC, targeting an inner
downsampling ratio of 9. However, the resulting BPIC was significantly different, indicating that code is much easier to
compress than Chinese. In terms of results, H-Net (2-stage) performs better than both H-Net (space) and BPE Transformer
on Chinese, which is reflected in the downstreams. On the other hand, H-Net (2-stage) achieves similar performance to
H-Net (space) on code, and both H-Net models perform significantly better than Transformer.
Model
Chinese
Code
BPIC
Main arch.
Val. BPB ↓
XW-zh. acc. ↑
BPIC
Main arch.
Val. BPB ↓
Transformer
3.62
T15
0.7404
0.599
3.58
T13
0.3376
H-Net
```

## `hnet-v2:s3.2:c0005` p.15 [caption] digit_ratio=0.068
```
H-Net ( M3T1 + T15 + M4 )
64M
2.705
H-Net ( M3T1 + M15 + M4 )
66M
2.697
Table 5: Model details and final performance on
HG38. We trained two isotropic models and two H-Net
models, varying the main network architecture (Trans-
former or Mamba-2). Each H-Net model outperforms
the corresponding isotropic model. We empirically find
that the E0 = M3T1 encoder architecture slightly outper-
forms a pure Mamba-2 encoder E0 = M4 (Appendix E.3).
Training Base Pairs Seen
2.75
2.80
2.85
2.90
2.95
3.6x more data efficient than isotropic model
Perplexity on HG38
Transformer
Mamba-2
H-Net (Trans.)
H-Net (Mamba)
Figure 6: Scaling performance on HG38 during the stable
phase of training. Each H-Net model achieves the same pre-
decay perplexity of the corresponding isotropic model with
approximately 3.6× les
```

## `hnet-v2:s3.3:c0000` p.17 [caption] digit_ratio=0.094
```
For ablation studies, we employ H-Net at Large scale following the configurations in Table 1, training on 36B tokens
randomly sampled from FineWeb-Edu.
Importance of Components in H-Net.
Figure 7 illustrates the impact of each architectural component on both model
performance and compression ratio (𝐿𝑠+1/𝐿𝑠) stability during training. We conduct three targeted ablations: (i) using direct
upsampling ˜𝑧𝑡= ˆ𝑧𝑡by removing the smoothing module (w/o smoothing), (ii) replacing the routing module that is based on
scaled cosine similarity, with direct probability prediction from individual inputs (w/o cosine routing), and (iii) skipping the
straight-through estimator in equation (9) (w/o STE).
The smoothing module proves essential for stable training dynamics. Without this module, compression ratios
```

## `hnet-v2:s3.3:c0001` p.17 [caption] digit_ratio=0.13
```
25B
50B
75B
100B
125B
Total Training Bytes
0.36
0.38
0.40
0.42
0.44
Compression Ratio L2/L1
H-Net
w/o smoothing
w/o cosine routing
w/o STE
Figure 7: Ablation study on key H-Net components showing validation BPB (left) and compression ratios for the
first stage 𝐿1/𝐿0 (center) and second stage 𝐿2/𝐿1 (right) during training. Using H-Net (2-stage), we evaluate the impact of
removing three components: the smoothing module (w/o smoothing), the similarity-based routing module (w/o cosine
routing), and Straight-Through Estimator (w/o STE).
40B
60B
80B
100B
120B
140B
Total Training Bytes
0.80
0.82
0.84
0.86
0.88
0.90
0.92
0.94
Bits-per-byte
40B
60B
80B
100B
120B
140B
Total Training Bytes
0.21
0.22
0.23
0.24
Compression Ratio L1/L0
M4-M4
M2T1-T1M2
T1M2-M2T1
T2-T2
Figure 8: Encoder-decoder architectu
```

## `hnet-v2:s3.3:c0003` p.17 [numeric_dense,caption] digit_ratio=0.17
```
influences both compression efficiency and modeling capability. We systematically evaluate different ar-
chitectural combinations using H-Net (1-stage) while fixing all other configurations in Table 1 the same. Four distinct
encoder-decoder (E0-D0) pairings are tested: M4-M4, M2T1-T1M2, T1M2-M2T1, and T2-T2, where M denotes a Mamba-2
40B
60B
80B
100B
120B
140B
Total Training Bytes
0.82
0.84
0.86
0.88
0.90
0.92
0.94
Bits-per-byte
T2-T2
T1M2-M2T1
M2T1-T1M2
M4-M4
Figure 9: SpaceByte++ encoder-decoder architecture ab-
lation using raw byte inputs. We evaluate four encoder-
decoder (E0 −D0) configurations: M4-M4 , M2T1-T1M2 and
T1M2-M2T1, and T2-T2, where M denotes Mamba layers
and T denotes Transformer layers.
40B
60B
80B
100B
120B
140B
Total Training Bytes
0.825
0.850
0.875
0.900
0.925
0.950

```

## `hnet-v2:s3.3:c0005` p.17 [caption] digit_ratio=0.013
```
monotonically with increased
Mamba layer allocation, achieving optimal results with the highest compression efficiency in the pure Mamba configuration
(M4-M4). These findings align with recent research demonstrating SSMs’ advantages over Transformers for fine-grained
sequence modeling (Goel et al. 2022; Schiff et al. 2024), as corroborated by MambaByte’s superior performance over
LlamaByte in Figure 3.
A natural question arises: does the importance of Mamba layers (i) stem specifically from processing fine-grained byte
inputs, or (ii) because they are better for compressing information into the next stage, even at coarser input
resolutions? To investigate these hypotheses, we train a 1-stage H-Net on top of BPE-tokenized inputs processed by the
GPT-2 tokenizer. We then evaluate six differe
```

## `hnet-v2:s3.3:c0007` p.17 [caption] digit_ratio=0.1
```
decoder roles in
our hierarchical architecture (Gu 2025). Based on these findings, we employ Mamba layers throughout all encoders and
decoders in our final H-Net configuration, as detailed in Table 1.
50B
100B
150B
200B
250B
300B
Total Training Bytes
0.74
0.76
0.78
0.80
0.82
0.84
0.86
Bits-per-byte
H-Net (2-stage, hybrid)
H-Net (2-stage, T27)
Figure 11: Hybrid main network. Bits-per-byte during
the stable phase of training, for H-Net (2-stage) with Trans-
former main stage and with hybrid main stage. The hybrid
main stage scales better, similar to findings for standard
token-based language models. This finding suggests that
design principles for isotropic (tokenized) models can carry
over to choices of the main network.
40B
60B
80B
100B
120B
140B
Total Training Bytes
0.80
0.85
0.90
0.95
1.
```

## `hnet-v2:s3.3:c0009` p.17 [caption] digit_ratio=0.011
```
perform better for our choice of main
network (Figure 11).
Comparison to Mixture-of-Experts.
H-Net can be viewed as a form of dynamic sparsity similar to Mixture-of-Experts
(MoEs), in that they are able to improve performance by using more parameters, all while keeping the total FLOPs budget
constant. We were interested in understanding whether or not its performance benefits were simply due to increasing
sparsity. We compare against a sparsified version of LlamaByte (byte-level isotropic Transformer model) at the Large scale
with a standard Mixture-of-Experts recipe (Fedus, Zoph, and Shazeer 2022) and similar parameter count as ours (Figure 12).
While sparsity does improve LlamaByte performance, it is still far worse than either FLOPs-matched H-Net (1-stage) or
H-Net (2-stage), even with 
```

## `hnet-v2:s3.3:c0010` p.17 [caption] digit_ratio=0.007
```
methods.
Table 6: Related architectures. Comparison of related architectures, particularly those focused on byte-level modeling.
H-Net is the first architecture that enables dynamic, multi-stage hierarchies. Extended discussion is provided in Appendix A.
Class
Autoregressive
Chunking Mechanism
Multi-stage
Example Architectures
Hierarchy
Isotropic
ByT5
MambaByte
Hierarchical (static)
𝑘-width pooling
Funnel-Transformer
Canine
Charformer
𝑘-width pooling
Hourglass Transformer
SaShiMi
MegaByte
Block Transformer
MBLM
AU-Net 3
Hierarchical (external)
delimiters
eByte
WSF
delimiters
DPT (Whitespaces)
SpaceByte
AU-Net 2
entropy
DPT (Entropy)
BLT
Hierarchical (dynamic)
soft matching
MANTa
soft gating
MrT5
stochastic reparameterization
DPT (Gumbel)
Hierarchical (dynamic)
dynamic chunking
H-Net
```

## `hnet-v2:s5:c0029` p.23 [caption] digit_ratio=0.013
```
in motivation that influences design considerations and downstream evaluations.
• Appendix A.3 mentions other works in non-language modalities related to tokenization.
We summarize our discussion on tokenizer-free architectures in Table 6.
A.1
Autoregressive Tokenizer-free Architectures
As outlined in Section 1, prior work on autoregressive tokenizers for architectures can be divided into four categories:
1. Non-hierarchical isotropic architectures.
2. Hierarchical architectures with static chunking strategies, where chunk boundaries are content-agnostic (usually
some variant of fixed-width pooling).
3. Hierarchical architectures with external chunking strategeies, where chunk boundaries are provided by an external
function or module.
4. Hierarchical architectures with dynamic chunking str
```

## `hnet-v2:s5:c0046` p.23 [equation] digit_ratio=0.041
```
× d_model × (2 × d_state + num_heads)
– SSD: 2 × 3 × seq_len × (expand × d_model) × d_state
– Depthwise Convolution: 2 × seq_len × d_model × window_size
– Gating: 5 × seq_len × d_model
– Output projection: 2 × seq_len × d_model × d_model
• Gated MLP:
– In, Gate, Out projections: 2 × seq_len × (3 × d_model × ffw_size)
– Gating: 5 × seq_len × d_model
• Logit Prediction Head: 2 × seq_len × vocab_size × d_model
We assume the backward pass consumes twice the FLOPs of the forward pass.
Learning Rate Modulation
As discussed in Section 2.3, we employ modulated learning rates for each stage by multiplying a scalar 𝜆𝑠to the base
learning rate. Empirically, we find that a reasonable set of multipliers (e.g., 𝜆0 = 2.0, 𝜆1 = 1.5, 𝜆2 = 1.0) works well in general.
To provide a more systematic experimenta
```

## `hnet-v2:s5:c0047` p.23 [caption] digit_ratio=0.054
```
al. 2025), and
(2) inverse square root of hidden dimension (Vaswani et al. 2017; Yang and Hu 2020). Concretely, without heavy manual
tuning, we define 𝜆𝑠as follows:
𝜆𝑠=
𝑁GPT ·
𝑖=𝑠𝑁𝑖
𝑖=0 𝑁𝑖· 𝐷S
𝐷𝑠,
𝑁𝑆= 1.0
(11)
Mean/Max
Pooling
(b)
Cross Attention
Pooling
(c)
(a)
Default
60B
80B
100B
120B
140B
Total Training Bytes
0.79
0.80
0.81
0.82
0.83
0.84
Bits-per-byte
XAttn + Res
XAttn
Max + Res
Max
Mean + Res
Mean
Base
Figure 13: Compression Methods in chunking layer. Default: H-Net’s Downsample operation (left-a). Max/Mean:
Channel-wise max and mean pooling within boundaries (left-b). XAttn: Cross-attention pooling within boundaries (left-c).
+Res: Adds boundary vector residuals to compressed outputs.
where 𝑁GPT is the average number of bytes per token of training dataset, which is 4.6 for the GPT-2
```

## `hnet-v2:s5:c0049` p.23 [caption] digit_ratio=0.088
```
channel-wise max/mean pooling and cross-attention, all applied to vectors within the same boundary.
Despite its simple design, the default compression in H-Net performs on-par with the other variants as demonstrated
in Figure 13-right. This shows that the sequence mixing layers in encoder are trained to implicitly compress necessary
context into vectors at boundaries, without explicit compression mechanisms such as pooling or cross-attention.
Model
Architecture
Params.
Final ppl. ↓
H-Net
M3T1 + T15 + M4
64M
2.705
H-Net
M3T1 + M15 + M4
66M
2.697
H-Net
M4 + T15 + M4
62M
2.722
H-Net
M4 + M15 + M4
64M
2.706
H-Net
M4 + T1M13T1 + M4
64M
2.706
Table 7: Encoder architecture ablations on HG38.
Switching the encoder architecture from M3T1 to M4
leads to worse performance across the board, though the
```

## `hnet-v2:s5:c0050` p.23 [caption] digit_ratio=0.035
```
Training Base Pairs Seen
2.75
2.80
2.85
2.90
2.95
Perplexity on HG38
H-Net (T1M13T1)
H-Net (Trans.)
H-Net (Mamba)
Figure 14: Mamba-2-only encoder loss curves during the
stable phase of training. The pure Mamba-2 model is more
unstable with a loss spike. Adding Transformer layers to the
main network near the DC modules can alleviate instabilities.
H-Net (1-stage, principled) corresponds to the T1M13T1
main network architecture.
E.2
Details of Chinese and Code Experiments
In Section 3.2, we analyzed the performance of H-Net (2-stage) against Transformer and H-Net (space) on Chinese and on
code, finding superior scaling for H-Net (2-stage) versus the other architectures. Here, we describe additional details from
the experiment.
Besides measuring scaling behavior, we also measured final checkp
```

## `hnet-v2:s5:c0051` p.23 [caption] digit_ratio=0.024
```
matched the settings from the GPT-3 XL, including 𝑑model and encoder/decoder
architecture for H-Net models. However, we adjusted the number of layers in the main network of each model to account
for slightly different compression ratios. Specifically, the Chinese-language models used a slightly higher total training
flops target than the original language models, while the code models used a lower flops target. Full architecture details
and results are also in Table 4.
E.3
DNA Architecture Ablations
H-Net (1-stage) with an M3T1 encoder achieves 3.6× the data efficiency of an isotropic architecture (Figure 6). As
mentioned in the caption of Table 5, we found that an M3T1 encoder outperformed a pure Mamba-2 M4 encoder
(Table 7). Putting a Transformer in the encoder network does not appear to
```

## `hnet-v2:s5:c0052` p.23 [caption] digit_ratio=0.026
```
more unstable. We then also
tried replacing the M15 in the main network with a T1M13T1 architecture, inspired by the finding that Transformer
layers are good for dealing directly with compressed input (see Figure 10). The new, principled main network architecture
improved stability greatly (Figure 14).
Distilling Token-Level Models to Byte-Level
The role of the outer stages in H-Net is analagous to that of the tokenizer, embedding module, and LM head in a traditional
BPE-based language model; together, these modules interconvert between raw text and an embedding space that the main
model backbone can process. Given this similarity, we investigated whether it would be possible to convert a BPE-tokenized
model directly into a byte level H-Net. To do this, we trained a 1-stage H-Net with froz
```

## `hnet-v2:s5:c0053` p.23 [caption] digit_ratio=0.015
```
Llama model has a hidden dimension of 3072, we add MLP adapters with
Ground Truth
Boundaries
BCE Loss
Ground Truth
Embeddings
Copy + Shift
MSE Loss
Figure 15: Auxiliary loss strategy for training the encoder of a H-Net with pretrained main stage. In order to mimic
the behavior of the tokenizer + embedding layer of a pretrained language model, we add supervision to both the routing
module boundary probabilities and to the hidden states that we pass through to the main network. These losses encourage
the encoder to tokenize once at the start of every token, while also passing the correct embedding into the main network
near the start of the token, thus making maximal use of the next-token prediction ability.
Table 8: Distilling Llama 3.2 3B to a byte level model. Average acc indicates averag
```
