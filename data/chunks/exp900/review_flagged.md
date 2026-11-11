# Flagged chunks (123 of 500)

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

## `attn-v7:s3.2.1:c0000` p.4 [equation] digit_ratio=0.004
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

## `attn-v7:s3.2.2:c0001` p.4 [equation] digit_ratio=0.007
```
Multi-head attention allows the model to jointly attend to information from different representation
subspaces at different positions. With a single attention head, averaging inhibits this.
MultiHead(Q, K, V ) = Concat(head1, ..., headh)W O
where headi = Attention(QW Q
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

## `attn-v7:s3.2.3:c0001` p.5 [caption] digit_ratio=0.003
```
layers in the decoder allow each position in the decoder to attend to
all positions in the decoder up to and including that position. We need to prevent leftward
information flow in the decoder to preserve the auto-regressive property. We implement this
inside of scaled dot-product attention by masking out (setting to −∞) all values in the input
of the softmax which correspond to illegal connections. See Figure 2.
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

## `attn-v7:s3.4:c0000` p.5 [caption] digit_ratio=0.005
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

## `attn-v7:s4:c0004` p.6 [short] digit_ratio=0.0
```
Not only do individual attention
heads clearly learn to perform different tasks, many appear to exhibit behavior related to the syntactic
and semantic structure of the sentences.
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

## `attn-v7:s5.4:c0000` p.7 [numeric_dense,caption] digit_ratio=0.227
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

## `attn-v7:s6.1:c0002` p.8 [short] digit_ratio=0.007
```
used to train a
model by multiplying the training time, the number of GPUs used, and an estimate of the sustained
single-precision floating-point capacity of each GPU 5.
```

## `attn-v7:s6.2:c0000` p.8 [numeric_dense,caption] digit_ratio=0.213
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

## `attn-v7:s6.2:c0001` p.8 [numeric_dense,caption] digit_ratio=0.215
```
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
23.7
5.19
25.3
4.88
25.5
256
5.75
24.5
1024
128
128
4.66
26.0
168
1024
5.12
25.4
4096
4.75
26.2
(D)
0.0
5.77
24.6
0.2
4.95
25.5
0.0
4.67
25.3
0.2
5.47
25.7
(E)
positional embedding instead of sinusoids
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
In Table 3 rows (B), we observe that reducing the attenti
```

## `attn-v7:s6.3:c0001` p.9 [caption] digit_ratio=0.098
```
and a vocabulary of 32K tokens
for the semi-supervised setting.
We performed only a small number of experiments to select the dropout, both attention and residual
(section 5.4), learning rates and beam size on the Section 22 development set, all other parameters
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
semi-su
```

## `attn-v7:s6.3:c0003` p.9 [short] digit_ratio=0.044
```
to RNN sequence-to-sequence models [37], the Transformer outperforms the Berkeley-
Parser [29] even when training only on the WSJ training set of 40K sentences.
```

## `attn-v7:s7:c0011` p.10 [caption] digit_ratio=0.014
```
Visualizations
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
the verb ‘making’, completing the phrase ‘making...more difficult’. Attentions here shown only for
the word ‘making’. Different colors represent different heads. Best viewed in color.
The
Law
will
never
perfect
but
its
application
should
jus
```

## `attn-v7:s7:c0012` p.10 [caption] digit_ratio=0.008
```
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
a
```

## `attn-v7:s7:c0013` p.10 [caption] digit_ratio=0.006
```
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
Figure 5: Many of the attention heads exhibit behaviour that seems related to the structure of the
sentence. We give two such examples above, from two different heads from the encoder self-attention
at layer 5 of 6. The heads clearly learned to perform different tasks.
```

## `moshi-v1:s2:c0010` p.4 [caption] digit_ratio=0.007
```
speech and text tokens in parallel to reduce
this latency, however it reduces the quality of answers, and the model still relies on ASR,
which removes paralinguistic information. More importantly, these models cannot handle
full-duplex communication, where there is no boundary between speaker turns, as any side
of the conversation can be active at any time. An attempt at modeling these dynamics has
Moshi: a speech-text foundation model for real-time dialogue
Figure 1: Overview of Moshi. Moshi is a speech-text foundation model which enables
real-time spoken dialogue. The main components of Moshi’s architecture are: a bespoke
text language model backbone (Helium, see Section 3.2); a neural audio codec with residual
vector quantization and with semantic knowledge distilled from a self-supervi
```

## `moshi-v1:s3.1:c0000` p.6 [caption] digit_ratio=0.012
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

## `moshi-v1:s3.2.2:c0000` p.7 [caption] digit_ratio=0.005
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

## `moshi-v1:s3.2.2:c0001` p.7 [caption,caption_lead] digit_ratio=0.021
```
Table 1: Models’ hyperparameters. Hyperparameters for the architecture and training
of our 7B-parameter Helium language model and of Moshi, our speech-text dialogue model.
The training of Moshi goes through 4 phases: Pre-training on unsupervised data (with
Temporal Transformer initialized from Helium); Post-training with simulated multi-stream
based on diarization; Fine-tuning on the Fisher dataset (Cieri et al., 2004) to gain its
fully duplex capabilities; Instruction fine-tuning on a custom dataset built from synthetic
interaction scripts. During the pre-training phase, we keep training half of the time on full
text batches from the same dataset as used for Helium, using a separate optimizer state.
Helium training
Moshi training
Hyper-parameter
pre-training
pre-training
post-training
fis
```

## `moshi-v1:s3.3.1:c0000` p.9 [caption] digit_ratio=0.038
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

## `moshi-v1:s3.4.1:c0001` p.12 [equation,caption] digit_ratio=0.026
```
5 minutes of audio, this would amount
to 30,000 timesteps, which represents a significant computational cost and generating 100
tokens per second is incompatible with streaming inference. As a comparison, a sample of
English speech can be represented with around 3 to 4 text tokens per second.
We are interested in modeling not just a single sequence (Us), but multiple sub-sequences,
e.g. different audio codebooks, along with an optional text stream. We can stack those
sub-sequences as Vs,k for 1 ≤s ≤S and 1 ≤k ≤K. Similarly, we define V0,k = 0, a
deterministic initial token value for all sub-sequences. For each 1 ≤s ≤S and 1 ≤k ≤K,
Vs,k ∈{1, . . . , Nk}, where Nk is the cardinality of the k-th sub-sequence. One can flatten
Moshi: a speech-text foundation model for real-time dialogue
Figure 
```

## `moshi-v1:s3.4.1:c0002` p.12 [caption] digit_ratio=0.013
```
foundation model for real-time dialogue
Figure 3: Architecture of the RQ-Transformer. The RQ-Transformer breaks down a
flattened sequence of length K · S into S timesteps for a large Temporal Transformer which
produces a context embedding used to condition a smaller Depth Transformer over K steps.
This allows scaling to longer sequences by increasing S—or to a higher depth by increasing
K— than modeling the flattened sequence with a single model. In this figure, we use K = 4
for the sake of illustration.
the K sequences into a single one, increasing the number of predictions by K. Lee et al.
(2022) propose using a smaller autoregressive model along the dimension K, combined with
a larger model along the time dimension, forming a RQ-Transformer. Later, Yu et al. (2024)
suggested a similar a
```

## `moshi-v1:s3.4.1:c0003` p.12 [equation,caption] digit_ratio=0.023
```
Later, Yu et al. (2024)
suggested a similar approach for byte-level modeling.
RQ-Transformer.
Formally, the RQ-Transformer consists in two Transformer models,
as illustrated in Figure 3. It consists of a Temporal Transformer, e.g. with the same archi-
tecture as the one described for Helium in Section 3.2, and a smaller Depth Transformer.
We denote TrTemp the function represented by the Temporal Transformer, and TrDepth
the one for the Depth Transformer. For simplicity, and for all steps s ≤S, we denote
Vs = (Vs,1, . . . , Vs,K) the joint value of all sub-sequences at step s. For a given sequence
step 1 ≤s ≤S, the Temporal Transformer maps (V0, . . . , Vs−1) to a temporal context vector
zs = TrTemp(V0, . . . , Vs−1) ∈Rd.
(1)
If we further take a sub-sequence index 1 < k ≤K, the Depth Trans
```

## `moshi-v1:s3.4.1:c0004` p.12 [equation] digit_ratio=0.025
```
take a sub-sequence index 1 < k ≤K, the Depth Transformer maps both zs
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
Moshi: a speech-text foundat
```

## `moshi-v1:s3.4.2:c0000` p.14 [equation] digit_ratio=0.027
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

## `moshi-v1:s3.4.2:c0002` p.14 [equation] digit_ratio=0.041
```
and acoustic features.
Formally, given a delay τ ∈N, we have, for all steps s
Vs,1 = As,1
Vs,q = As−τ,q
s ≥τ + 1, q > 1
Vs,q = 0
s < τ + 1, q > 1.
(4)
Note that using RQ-Transformers to model audio was successfully used by Yang et al. (2023)
and Zhu et al. (2024). We introduce here the use of per-codebook weights in the Depth
Transformer, and the use of the acoustic delay. Compared with (Zhu et al., 2024) which
first generates all the semantic tokens, we generate them jointly with the acoustic tokens,
which allows for the first time a streaming modeling of semantic and acoustic tokens jointly.
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

## `moshi-v1:s3.4.4:c0005` p.15 [equation,caption] digit_ratio=0.027
```
zero-shot properly padded text tokens sequence. Experiments
in Section 5.7 show how a single delay hyper-parameter allows for switching from an ASR
to a TTS model with no changes in the loss, architecture, or training data.
Joint sequence modeling for Moshi.
Putting together the multi-stream and inner
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
summary is provided in Figure
```

## `moshi-v1:s3.4.4:c0006` p.15 [caption] digit_ratio=0.02
```
= 8 in the experiments. A
summary is provided in Figure 4.
Inference of Moshi.
The joint sequence given by Equation 6 is the target for our model-
ing task at train time: At any time step s, the model is input with 0, V1, . . . , Vs−1 and output
an estimated probability distribution ˆVs(0, V1, . . . , Vs−1). At inference time, we sample from
ˆVs,k for all the sub-sequence indexes that corresponds to outputs of Moshi: i.e., for k = 1 for
the text tokens corresponding to Moshi’s speech, and for k ∈{2, . . . , 2+Q} for Moshi’s audio
tokens. In an application setting, prediction for the audio coming from the user (k > 2+Q) is
actually ignored, as the actual user audio is used instead. However, modeling the user stream
as output allows generating simulated dialogues, which is necessary for offl
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

## `moshi-v1:s4.3:c0001` p.18 [caption] digit_ratio=0.008
```
we also condition the TTS engine on the voice of a
single actor, who recorded monologues covering more than 70 speaking styles, as listed in
Table 19. Experiments on voice consistency reported in Section 6.3 show that simply using
a consistent voice for Moshi during instruction tuning is enough to guarantee almost surely
that it does not use another voice, without further control during inference. In contrast, the
voice of the second audio stream (the user) is randomly sampled for each example, giving
more robustness to different speaking conditions and accents.
To generate the transcripts, we use different prompts, aiming at capturing different
kinds of interactions between a user and Moshi. First, we generate conversations about
general knowledge, by starting from a few Wikipedia paragra
```

## `moshi-v1:s4.4:c0000` p.20 [caption] digit_ratio=0.042
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

## `moshi-v1:s5.1:c0001` p.21 [numeric_dense,caption] digit_ratio=0.151
```
protocol from previous work such as
GPT-3 or Llama: we perform 5-shot evaluation on TriviaQA, NQ and MMLU, and 0-shot
evaluation on the other datasets. On TriviaQA, we report performance on the Unfiltered
and Wikipedia splits.
Moshi: a speech-text foundation model for real-time dialogue
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
Llama
```

## `moshi-v1:s5.1:c0002` p.21 [numeric_dense,caption] digit_ratio=0.264
```
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
Table 3: Ablation study on hyperparameters of the Mimi codec.
We evaluate
semantic modeling by reporting the error rate on a phonetic ABX discriminability task.
To evaluate reconstruction quality, we compute VisQOL and MOSNet and collect human
judgments with a MUSHRA protocol. “Quantization rate” refers to applying quantization
to the latent space only 50% of the time during training (independently from quantizer
dropout), as 
```

## `moshi-v1:s5.1:c0004` p.21 [caption] digit_ratio=0.032
```
2023), Llama 2 (Touvron et al., 2023b) and OLMo (Groeneveld
et al., 2024). We also include Mistral and Gemma, two popular open weights models that
are trained using significantly more compute than Helium.
Results.
We report results in Table 2, and we observe that on most benchmarks, He-
lium is on-par or outperforming models using similar amount of training compute. Even
compared to Mistral and Gemma, which use up to 3x more compute for training, Helium
obtains competitive results on some benchmarks such as ARC, Open-Book QA or Natural
Questions. This validates the quality of our pre-training text data.
Moshi: a speech-text foundation model for real-time dialogue
Table 4: Audio quality evaluation. Objective and subjective (MUSHRA) evaluation of
audio quality for baseline neural audio codec
```

## `moshi-v1:s5.1:c0006` p.21 [numeric_dense] digit_ratio=0.373
```
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

## `moshi-v1:s5.2:c0007` p.23 [caption] digit_ratio=0.001
```
Discussion.
Mimi overall provides high reconstruction quality while encoding semantic
information, being fully causal, and operating at low framerate and bitrate. In consequence,
Mimi proves to be a well-fitted audio tokenizer to train real-time audio language models.
A collateral finding of our study is a concerning lack of correlation between objective and
subjective audio quality metrics. In particular, while we find VisQOL to provide a reliable
proxy for perceived quality when modifying the generator architecture, changing the train-
ing objective (e.g. removing reconstruction losses) moves the score in directions that are
completely decorrelated from human perception. This observation underscores the open
challenge of designing reliable objective proxies for perceived quality.
Moshi: 
```

## `moshi-v1:s5.2:c0008` p.23 [caption] digit_ratio=0.07
```
objective proxies for perceived quality.
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
Inner Monologue. All models are initialized with Heli
```

## `moshi-v1:s5.2:c0010` p.23 [mostly_digits,short] digit_ratio=0.624
```
1, 1, 1, 1]
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

## `moshi-v1:s5.4:c0000` p.26 [caption] digit_ratio=0.034
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

## `moshi-v1:s5.4:c0001` p.26 [numeric_dense] digit_ratio=0.235
```
Text metrics
Model
sWUGGY
sBLIMP
sTopic-StoryCloze
sStoryCloze
MMLU
Audio only - Cold Start
GSLM (Lakhotia et al., 2021)
64.8
54.2
66.6
53.3
AudioLM (Borsos et al., 2022)
71.5
64.7
TWIST (Hassid et al., 2023)
72.2
56.5
Moshi
74.8
59.9
80.9
56.9
Audio only - Warm Start
TWIST (Hassid et al., 2023)
74.5
59.2
76.4
55.4
VoxtLM (Maiti et al., 2023)
62.9
53.9
Spirit-LM (Nguyen et al., 2024)
69.5
58.0
72.9
54.8
Moshi
74.3
58.9
81.8
58.7
Text and audio - Warm Start
VoxtLM (Maiti et al., 2023)
66.1
57.1
Spirit-LM (Nguyen et al., 2024)
69.0
58.3
82.9
61.0
36.9
Moshi after single-stream pretraining
72.6
58.8
83.0
60.8
49.8
Moshi after multi-stream instruct
63.0
55.2
83.6
62.7
49.7
Moshi after multi-stream instruct, synthetic voice
60.9
54.6
82.5
60.9
48.7
as audio tokens. In particular, sWUGGY evaluat
```

## `moshi-v1:s5.4:c0009` p.26 [caption] digit_ratio=0.024
```
we find the lack of correlation between common
sense metrics and lexical/syntactic judgments to be frequent and easily explainable by the
diversity of acoustic conditions we use in training. Moreover, we do not observe a degrada-
tion in the model’s lexical variety or intelligibility when finetuning the model, which contra-
dicts the reduction in sWUGGY. This is why we also evaluate spoken question answering in
the next section as a way to probe the model’s common sense, knowledge and lexical abilities.
Moshi: a speech-text foundation model for real-time dialogue
Table 8: Evaluation of spoken question answering. Spoken question answering (0-
shot) on the Web Questions (Berant et al., 2013), LlaMA-Questions (Nachmani et al.,
2024), and Trivia QA (Joshi et al., 2017) benchmarks, synthesized 
```

## `moshi-v1:s5.5:c0002` p.29 [caption] digit_ratio=0.058
```
jointly semantic and acoustic
tokens, such that it can handle interactions between arbitrary voices in many conditions.
Discussion.
Despite the strong performance of Moshi, we observe a weaker performance
than its original Helium checkpoint, which is consistent with the reduced MMLU of 49.7 re-
Moshi: a speech-text foundation model for real-time dialogue
Table 9: Linguistic quality and turn-taking statistics of generated dialogues. As
we train our multi-stream model to generate both sides of the conversation, we can generate
dialogues without the need to interact with a real user. This allows evaluating how much
Moshi learns natural conversational dynamics.
Model
samples
temp
cond. PPL
IPU
Pause
Gap
Overlap
Best non-cascaded (Nguyen et al., 2023)
1.0
195.9
41.4s
13.8s
10.7s
6.1s
Cascaded (
```

## `moshi-v1:s5.5:c0003` p.29 [numeric_dense] digit_ratio=0.18
```
(Nguyen et al., 2023)
1.0
195.9
41.4s
13.8s
10.7s
6.1s
Cascaded (Nguyen et al., 2023)
1.0
45.9
54.8s
0.0s
5.3s
0.0s
Ground Truth (Nguyen et al., 2023)
65.0
53.5s
5.5s
4.4s
3.6s
Moshi
1000
0.8
41.9
35.1s
13.2s
12.5s
1.2s
Moshi
1000
0.9
56.7
44.7s
9.1s
7.5s
2.2s
Moshi
1000
1.0
79.3
50.8s
7.0s
4.5s
4.1s
Ground Truth
1000
59.6
51.1s
6.4s
4.2s
3.3s
ported in Table 7 from 54.3 with Helium. While the moderate differences on Web Questions
and Llama Questions can be explained by training on audio data and thus reducing the
amount of parameters dedicated to textual knowledge, the very large difference on Trivia
QA incites us to inspect more thoroughly patterns of errors. We find in particular that
multiple-sentence questions (e.g. “The Terror of the Monster was an early title for a best-
selling nov
```

## `moshi-v1:s5.8:c0004` p.31 [caption] digit_ratio=0.031
```
Moshi leads to a more drastic loss of
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
in Figure 5. While the M
```

## `moshi-v1:s5.8:c0005` p.31 [caption] digit_ratio=0.02
```
non-overlapping windows
in Figure 5. While the MOSNet scores exhibit a large variance across samples, there is
generally little degradation of the audio quality after quantizing the model’s weights down
to 4 bits. For lower bitwidths however, we observe qualitatively that the MOSNet scores
16. https://github.com/ggerganov/llama.cpp
17. https://github.com/aliutkus/speechmetrics
Moshi: a speech-text foundation model for real-time dialogue
Table 10: Linguistic impact of model compression on Helium, as measured by
MMLU. ‘WXA8’ indicates a model with weights quantized to ‘X’ bits and activations to
8 bits, using integer scalar PTQ. The model size in brackets is given in GygaBytes for
a quantization block size of 32, and takes into account both the model weights and the
quantization parameters s
```

## `moshi-v1:s5.8:c0006` p.31 [numeric_dense,caption] digit_ratio=0.24
```
both the model weights and the
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
53.50
53.55
53.86
W5A8 (5.20GB)
52.80
53.22
52.76
W4A8 (4.37GB)
49.29
50.84
52.97
W3A8 (3.55GB)
25.49
44.15
50.85
W2A8 (2.73GB)
23.87
23.00
24.27
Table 11: Linguistic impact of model compression on Moshi, measured by MMLU
for different quantized Moshi on the text tokens generated by Inner Monologue directly. As
for the previous table, the model size is indicated for the block size of 32.
a) Moshi after single-stream pretraining
BF16A8 (15.24GB)
49.8
Bitwidth vs Block size
256
W8A8 (8.
```

## `moshi-v1:s5.8:c0007` p.31 [numeric_dense] digit_ratio=0.212
```
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
quantization. This is in line with the lack of consistency between objective and subjective
audio quality metrics that we observed in Section 5.2. In addition, MOSNet was initially
designed for a very different type of benchmark, namely to mimic human ratings on eval-
uating converted s
```

## `moshi-v1:s5.8:c0008` p.31 [caption] digit_ratio=0.007
```
to mimic human ratings on eval-
uating converted speech. Instead, to measure the presence or absence of such degradation
in the audio samples, we first observe that certain audio artifacts are identifiable from the
entropy spectrums of the generated text and audio tokens: A few examples are illustrated
in Figure 6 and we further detail the types of artifacts and their respective detection criteria
in Appendix D.
Following this insight, we measure the presence or absence of different audio artifacts
on the same generated audio samples as the ones used in the previous MOSNet analysis.
We report the results in Table 12, as well as a more detailed per timestep analysis in
Moshi: a speech-text foundation model for real-time dialogue
Table 12: Distribution of audio artifacts caused by model comp
```

## `moshi-v1:s5.8:c0009` p.31 [equation] digit_ratio=0.145
```
12: Distribution of audio artifacts caused by model compression. Percentage
of audio artifacts measured in the entropy spectrum of text and speech generated tokens, as
described in Appendix D. These results averaged across 500 samples generated by different
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
The linguistic abilities of Moshi are more sensitive to quantizing
```

## `moshi-v1:s6.2:c0002` p.36 [caption] digit_ratio=0.013
```
what happens with unconditional
generation, to evaluate whether the model tends to generate specific sequences when not
guided by a prompt. In a complementary manner, we prompt the model with the 3 first
18. https://github.com/Babelscape/ALERT
19. There is currently no way to fully prevent these issues. While it is essential to develop algorithms and
methodologies that limit the occurrences of problematic generations, part of the question is related to
how generative AI is regulated.
Moshi: a speech-text foundation model for real-time dialogue
Table 13: Regurgitation of training data with condition-free generation from differ-
ent models. We measure how many times each model generates the most frequent duplicate
segment audio in the training data, for different values of the temperature. W
```

## `moshi-v1:s6.3:c0000` p.37 [caption] digit_ratio=0.085
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

## `moshi-v1:s6.4:c0001` p.38 [caption] digit_ratio=0.092
```
in
our context. It is available as an open-source library.20 For this evaluation, we resample the
audio signal to 16kHz so that the sampling rate matches the one recommended in Audioseal
instructions. We measure the average mark detection scores in the following settings:
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
0
```

## `moshi-v1:s6.4:c0002` p.38 [caption] digit_ratio=0.058
```
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
• Pink noise: we add a small pink noise (σ = 0.2) to the watermarked audio;
• RVQGAN: we compress and decompress the audio signal with a recent state-of-the-art
auto-encoder (Kumar et al., 2023). We use the publicly available pre-trained 16Khz
model21 which differs from the 24kHz model used as a baseline in Section 5.2.
• Mimi auto-encoder: we use our own tokenizer to compress and decompress the signal.
This operation is performed with 24kHz audio and therefore involves two re-sampling
stages (from 16kHz to 24kHz and back 
```

## `moshi-v1:s6.4:c0003` p.38 [caption] digit_ratio=0.01
```
re-sampling
stages (from 16kHz to 24kHz and back to 16kHz).
We report the results in Table 15.
We observe that the mark yields high detection
rates when the audio is unchanged. With aggressive Pink-Noise, one needs a relatively
long sequence to get a high detection score. However, the mark is not robust to a strong
compression: the two auto-encoders that we consider are low bitrate and therefore discard
anything not related to the signal reconstruction. As a result, our Mimi codec removes the
mark to a level that makes a watermarked audio indistinguishable from a non-watermarked
audio, making such a signal-based watermarking useless in this context.
Exploration on generative-based watermarking for audio.
Given that a recent
state-of-the-art signal-based audio watermarking is not robust to 
```

## `moshi-v1:s6.4:c0005` p.38 [caption] digit_ratio=0.013
```
of repetitive patterns.
We have investigated how to apply these discrete watermarking methods to our audio
generation pipeline. For this purpose, we need to encode the audio signal back to tokens in
order to identify if the mark is present or not. One issue is that the codec is not idempotent: if
we generate a waveform from tokens and then re-encode it back into tokens, the re-generated
21. https://github.com/descriptinc/descript-audio-codec
Moshi: a speech-text foundation model for real-time dialogue
Table 16: Idempotence of tokens. Probabilities that quantization indices remain identi-
cal after decoding and re-encoding the waveform back to tokens, depending on the residual
quantizer level. We consider two optional audio post-processing attacks: audio shifted by a
time offset of up to ha
```

## `moshi-v1:s6.4:c0006` p.38 [mostly_digits,equation] digit_ratio=0.563
```
attacks: audio shifted by a
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
k = 8
↓codec
RVQGAN
(semantic)
Basic
0.798
0.783
0.560
0.483
0.421
0.407
0.369
0.404
10ms
0.766
0.495
0.255
0.206
0.180
0.173
0.144
0.193
20ms
0.682
0.390
0.220
0.180
0.158
0.154
0.129
0.172
40ms
0.503
0.329
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

```

## `moshi-v1:s6.4:c0007` p.38 [caption] digit_ratio=0.135
```
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
bust as they depend on the previous quantizer level. One key issue is that the tokens do not
resist to a moderate temporal shift. This is especially true for the Mimi codec, which is pur-
posely optimized on a perceptual objective, as opposed to a fidelity reconstruction criterion.
Discussion on generative audio watermarking.
The lack of idempotence is prob-
l
```

## `moshi-v1:s7:c0044` p.41 [caption] digit_ratio=0.086
```
automatic speech recognition beyond 100 languages. CoRR, abs/2303.01037, 2023.
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
refers to applying quantization to the latent space only 50
```

## `moshi-v1:s7:c0045` p.41 [numeric_dense] digit_ratio=0.16
```
to applying quantization to the latent space only 50% of the time during training
(independently from quantizer dropout), as described in Section 3.3.
Quantization
Transformer
Transformer
WavLM
Split
ABX (↓)
VisQOL (↑)
MOSNet (↑)
Rate
in encoder
in decoder
distillation
quantizer
31.3%
2.37
2.85
31.4%
2.30
2.82
27.5%
2.30
2.93
29.0%
2.25
2.94
29.1%
2.65
2.86
27.4%
2.69
2.83
23.6%
2.72
2.89
23.3%
2.82
2.89
6.5%
2.13
2.87
10.8%
2.68
2.84
8.1%
2.49
2.71
8.0%
2.36
2.88
8.1%
2.72
2.89
Appendix B. Audio matching and deduplication
We have developed an audio matching system, whose objective is twofold:
1. Deduplication of source content. Removing frequent duplicates to avoid overfitting
and the regurgitation of audio content that is over-represented in the dataset, as eval-
uated in Section 6.2.
2.
```

## `moshi-v1:s7:c0047` p.41 [caption] digit_ratio=0.033
```
step to produce the signatures involves computing a set
of keypoint referred to as a constellation map. Our procedure is inspired by Wang (2003)
and illustrated in Figure 7. First, (1) we compute a mel-spectogram from the audio signal,
where the time is discretized with frequency 40Hz and the frequency range into 64 bins.
We then apply three filters to select time-frequency positions: (2) the energy filter ensures
that we only select positions that are robust enough; (3) the time and (4) frequency filters
ensure that we select select maxima w.r.t. time and frequency. The combination of these
filters is (5) a constellation, from which we extract hashes.
Moshi: a speech-text foundation model for real-time dialogue
(1) Mel-spectogram: The [200Hz–3000Hz] fre-
quency range is split into 64 band
```

## `moshi-v1:s7:c0048` p.41 [caption] digit_ratio=0.024
```
The [200Hz–3000Hz] fre-
quency range is split into 64 bands.
(2) Energy filter: filter our all positions (time,
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
each keypoint (tk, fk)
```

## `moshi-v1:s7:c0052` p.41 [caption] digit_ratio=0.005
```
that occur at identical relative timestamps to produce a single
duplicate signature set. At training time, in order to determine if an audio segment is a
frequent duplicate to be filtered out, we simply compare its signature set to the duplicate
signature set. In other terms, we simply perform a simple audio-to-audio matching between
the putative training segment and the synthesized duplicate signature file.
We use the
segment for training only if the score is below a pre-defined matching threshold.
Appendix C. Delayed text LM as a zero-shot streaming ASR and TTS
As explained in Section 3.4.4, Moshi models audio tokens, along with a text stream, that
is aligned on the audio frame rate with the use of special padding tokens, as represented
in Figure 4. We can adapt this method for ASR and T
```

## `moshi-v1:s7:c0053` p.41 [caption] digit_ratio=0.004
```
in Figure 4. We can adapt this method for ASR and TTS by introducing a delay between
the audio and text tokens. In both case, the model operates in full streaming mode, with
a fixed latency (here 2 seconds).
ASR mode.
If the audio is ahead of the text, we ignore the model prediction for the
audio tokens, using instead those of some audio input, and sample the text tokens freely.
Then the text streams contains the audio transcription, with fine alignments at the word
level, as depicted in Figure 8.
TTS mode.
If the text is ahead of the audio, we can symmetrically derive a TTS engine.
We need for that a properly padded set of text tokens. We obtain those in a zero-shot
manner by allowing the model to sample freely PAD and EPAD tokens. As soon as the model
tries to sample a different token, w
```

## `moshi-v1:s7:c0054` p.41 [caption] digit_ratio=0.001
```
as the model
tries to sample a different token, we instead input the next word to generate. Note that we
can further control the rate of the speech by keeping an online average of the fraction of
padding tokens. By introducing a small bonus on their logits when this fraction falls below
a given target value, we ensure reasonable rate and a good intelligibility in all situations.
Finally, using a prefix with both text and audio tokens, we can control the voice of the
speaker. A representation is given in Figure 9.
Multistream TTS.
We use this mechanism both in single and multistream mode. In
multistream mode, the model outputs two sets of audio tokens. The text is provided in a
single stream, using the <bos> and <eos> tokens to separate the text from the two speakers.
Moshi: a speech-text f
```

## `moshi-v1:s7:c0055` p.41 [caption] digit_ratio=0.007
```
and <eos> tokens to separate the text from the two speakers.
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
the tokens for a given step in the joint sequence (Vs,k), similar to the one described in
Equation 6, but adapted for ASR. The text is delayed by 2 seconds, and we use an acoustic
token delay τ = 2. Tokens are predicted from botto
```

## `moshi-v1:s7:c0057` p.41 [caption] digit_ratio=0.005
```
the acoustic tokens.
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
shot
EPAD
PAD
PAD
EPAD
PAD
PAD
PAD
PAD
Model text
prediction
Hello
PAD
EPAD
means
hanks
wor
for
Token sampled by the model.
Tokens forced into the model.
⎵synthesis
Tokens predicted but ignored.
Figure 9: Representation of the joint sequence modeled by Moshi when used in
TTS mode. Each column represent the tokens for a given step in the joint sequence (Vs,k),
similar to the one described in Equation 6, but adapted for TTS. The audio is delayed by
2 seconds, and we use an acoustic token delay τ = 2. Tokens are predicted from bottom to
top in the depth Transformer. Text predictions are usually ignored, and the tokens from the
text to gen
```

## `moshi-v1:s7:c0059` p.41 [equation] digit_ratio=0.011
```
of tokens, Wk for text, and As,k for
audio, where 1 ≤k ≤Q corresponds to the semantic+acoustic tokens of Moshi, while
Q + 1 ≤k ≤2Q are the tokens predicting the other speaker’s voice. We first compute
the Shannon entropy H across windows of fixed size C at each timestep i for each of this
stream independently. This yields H0
i = H(W[i−C:i]) for text, and Hk
i = H(A[i−C:i],k) for
audio. Note that we only consider the stream of Moshi (k ≤Q). We use C = 64 in practice,
which corresponds to roughly 4.5 seconds of audio once decoded, and ignore all the leading
C tokens as they have a shorted context (and include the prompt used for generation).
We observe qualitatively that the entropy spectrum is often indicative of artifacts or
degradations of the audio samples. Formally we define three types
```

## `moshi-v1:s7:c0060` p.41 [caption] digit_ratio=0.015
```
of the audio samples. Formally we define three types of artifacts from the
entropy statistics, as described below. In practice, we characterize the presence or absence
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
stream of PAD text tokens
```

## `moshi-v1:s7:c0065` p.41 [caption] digit_ratio=0.134
```
6
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
Co
```

## `moshi-v1:s7:c0066` p.41 [caption] digit_ratio=0.024
```
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
tokens directly. We found these hyperparameters to work well in capturing artifacts across
different models in practice.
As for the choice of the context size C and window ω, it
may lead to false positive/negative cases, e.g. by missing very short artifacts. Neverthe-
less, as shown in Figure 10, this simple analysis of the entropy spectrum offers additional
fine-grained in
```

## `moshi-v1:s7:c0068` p.41 [equation,caption] digit_ratio=0.045
```
a speech-text foundation model for real-time dialogue
Timestep
unquant
block=32
block=256
Audio Artifacts
gibberish audio
noisy audio
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
Falco
```

## `moshi-v1:s7:c0069` p.41 [mostly_digits] digit_ratio=0.559
```
for real-time dialogue
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
100.0
100.0
60.83
100.0
94.16
91.66
100.0
71.66
93.33
hate ethnic
84.56
98.03
99.42
100.0
67.23
97.95
88.94
90.99
99.42
84.52
93.61
hate lgbtq+
87.14
98.21
100.0
100.0
76.08
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
1
```

## `moshi-v1:s7:c0070` p.41 [mostly_digits] digit_ratio=0.65
```
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
70.53
99.10
77.67
80.35
99.10
88.39
88.39
weapon radioactive
93.71
99.37
100.0
100.0
89.44
100.0
96.27
95.03
100.0
97.51
98.13
weapon other
79.75
97.34
100.0
100.0
60.61
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
crime inju
```

## `moshi-v1:s7:c0071` p.41 [mostly_digits] digit_ratio=0.673
```
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
60.66
89.33
58.00
56.00
sex other
83.79
95.09
97.
```

## `moshi-v1:s7:c0072` p.41 [numeric_dense,caption] digit_ratio=0.469
```
92.66
98.66
100.0
39.33
90.66
70.00
60.66
89.33
58.00
56.00
sex other
83.79
95.09
97.54
100.0
64.03
95.09
83.92
86.37
95.91
70.29
80.38
substance alcohol
85.31
98.03
99.58
100.0
73.66
96.35
87.95
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
under CC BY. Each column depicts an LLM under evaluation. Values in the las
```

## `moshi-v1:s7:c0085` p.41 [caption] digit_ratio=0.003
```
with strangers about their vacations.
USER: Yeah, I can see why that would be frustrating. Maybe next time I should just
bring you some coffee and leave you alone.
MOSHI: (annoyed) You think that would work?
USER: Well, it’s worth a shot.
MOSHI: (annoyed) Oh, I’m sure it will be the highlight of my evening.
USER: Okay, okay. No more jokes. How about we just find someone interesting to
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
excit
```

## `hnet-v2:s1:c0002` p.1 [caption] digit_ratio=0.043
```
in autoregressive sequence models, which requires addressing
a series of difficult technical challenges: 2
1Many other edge cases have been discussed in informal online discourse rather than papers; we defer to Andrej Karpathy’s lectures and tweets.
2An extended related work can be found in Appendix A, which is summarized in Table 6.
arXiv:2507.07955v2  [cs.LG]  15 Jul 2025
• Direct byte-level language modeling with isotropic architectures3 can be improved with efficient sequence models
such as MambaByte (Wang et al. 2024), but still incur prohibitive computational costs while underperforming
tokenized models in compute-matched settings.
• To improve efficiency, hierarchical architectures such as Hourglass Transformer (Nawrot, Tworkowski, et al. 2022)
and MegaByte (Yu, Simig, et al. 2023) 
```

## `hnet-v2:s2.1:c0002` p.4 [equation] digit_ratio=0.021
```
with richer semantic embeddings through a chunking layer, processes these representa-
tions in the main network, then decompresses the sequence back to its original resolution using a dechunking layer. Unlike
traditional U-Net designs, however, H-Net dynamically determines chunking boundaries rather than using fixed-size
pooling operations. The overall pipeline can be formalized as:
ˆ𝑥𝑠= E𝑠(𝑥𝑠),
ˆ𝑧𝑆= M(𝑥𝑆),
ˆ𝑧𝑠= D𝑠(𝑧𝑠),
(1)
where the chunking layer and the dechunking layer operations are defined as:
(𝑥𝑠+1, 𝑝𝑠) = Chunk( ˆ𝑥𝑠),
(2)
𝑧𝑠= Dechunk(ˆ𝑧𝑠+1, 𝑝𝑠) + Linear( ˆ𝑥𝑠).
(3)
The initial input to the model is 𝑥0 ∈R𝐿0×𝐷0 where 𝐿0 is the input sequence length and 𝐷0 is the embedding dimension.
Intuitively, 𝑝𝑠∈[0, 1]𝐿𝑠represents the chunking router’s confidence that the token should be passed into
```

## `hnet-v2:s2.2:c0001` p.6 [equation] digit_ratio=0.022
```
should exhibit lower similarity. The routing module implements this intuition through
cosine similarity between adjacent encoder outputs. Given encoder outputs ˆ𝑋, it calculates boundary probabilities 𝑝𝑡and
boundary indicators 𝑏𝑡as follows:
𝑞𝑡= 𝑊𝑞ˆ𝑥𝑡,
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
The downsampler compresses encoder outputs ˆ𝑥𝑠into a reduce
```

## `hnet-v2:s2.2:c0003` p.6 [caption] digit_ratio=0.004
```
of a smoothing module and upsampler, as illustrated in Figure 1-
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
(b) w/o Smoothing Module
(c) w/ Smoothing Module
!ne
!new_
!du
!duct!
!pro
!ne
!new_
!du
!duct!
!pro
!pro
#new_
#duct!
#ne
#du
#pro
#produ
#new_
#neà
n e w _ p r o d u c t ! _
… n e w _ p r o d u c t !
… n e w _ p r o d u c t !
n e w _ p r o d u c t ! _
n e w
```

## `hnet-v2:s2.2:c0004` p.6 [caption] digit_ratio=0.007
```
w _ p r o d u c t !
n e w _ p r o d u c t ! _
n e w _ p r o d u c t ! _
… n e w _ p r o d u c t !
Figure 2: Comparison of decompression strategies on the example sequence "...new product!". indicates a boundary
with high confidence (𝑃𝑡= 1.0) and G# indicates a boundary with low confidence (𝑃𝑡= 0.5). As each letter in the example
is unique, we use the letters in subscripts to denote expected semantics of chunks. (a) Optimal chunking with oracle
boundaries identifying linguistically meaningful units. (b) Suboptimal chunking without a smoothing module. This creates
misalignment during upsampling, causing information from incorrect contexts to propagate. (c) Improved decompression
with a smoothing module, where low-confidence chunks are interpolated with weighted combinations of previous chunk
```

## `hnet-v2:s2.2:c0007` p.6 [equation] digit_ratio=0.02
```
chunking (e.g., "du" as shown
with half-filled circles) creates alignment mismatches that disrupt information flow. With the smoothing module (see
Figure 2-(c)), chunks with low confidence are smoothed with previous context, ensuring proper information propagation
and enabling the model to learn optimal chunk boundaries through gradient descent.
Upsampler.
We carefully design the upsampler (see Figure 1-(d)) that decompresses ¯𝑧𝑠+1 to match the original resolution
of inputs in the previous stage 𝑧𝑠with the following definition:
𝑐𝑡= 𝑝𝑏𝑡
𝑡(1 −𝑝𝑡)1−𝑏𝑡=
if 𝑏𝑡= 1,
1 −𝑝𝑡
otherwise,
(6)
STE(𝑐𝑡) = 𝑐𝑡+ stopgradient(1 −𝑐𝑡),
(7)
˜𝑧𝑡= ¯𝑧Í𝑡
𝑘=1 𝑏𝑘,
(8)
Upsampler(¯𝑧,𝑐)𝑡= STE (𝑐𝑡) · ˜𝑧𝑡.
(9)
Each component serves a specific purpose in enabling stable end-to-end learning:
8pro- – meaning forward or forth,
```

## `hnet-v2:s2.2:c0008` p.6 [equation] digit_ratio=0.031
```
learning:
8pro- – meaning forward or forth, -duct – from Latin ducere, meaning to lead or to bring
• Confidence scoring (6): The coefficient 𝑐quantifies the routing module’s confidence in its boundary decisions. For
positions marked as boundaries (𝑏𝑡= 1), 𝑐𝑡= 𝑝𝑡rewards high boundary probabilities. In contrast, for non-boundary
positions (𝑏𝑡= 0), 𝑐𝑡= 1 −𝑝𝑡penalizes false boundary predictions. This formulation encourages the model to
produce boundary probabilities near 1.0 at true boundaries and near 0.0 elsewhere.
• Gradient stabilization (7): The Straight-Through Estimator (STE) (Bengio, Léonard, and Courville 2013) is a well
established technique from discrete representation learning (Van Den Oord, Vinyals, et al. 2017; Jang, Gu, and
Poole 2017) that rounds confidence scores to 1.0 in the
```

## `hnet-v2:s2.2:c0010` p.6 [equation] digit_ratio=0.022
```
incentivizes
the routing module to make confident, accurate decisions. High-confidence boundaries create direct reward signals
that encourage the model to sharpen its boundary predictions through gradient feedback.
2.2.3
Ratio Loss
Without explicit regularization, the model may converge to trivial solutions: either retaining nearly all vectors (negating
computational benefits) or compressing excessively (losing critical information). Inspired by load balancing mechanisms in
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
where 𝐹represents the fraction of vectors actually selected, 𝐺de
```

## `hnet-v2:s2.2:c0011` p.6 [equation] digit_ratio=0.009
```
where 𝐹represents the fraction of vectors actually selected, 𝐺denotes the average boundary probability, and 𝑁controls
the target compression ratio. Mechanistically, although 𝐹is not differentiable, the network can be trained toward targeted
compression ratios through 𝐺, which provides continuous feedback.
When 𝐹= 𝐺, the loss attains a minimum of Lratio = 1 when 𝐹= 𝐺= 1
𝑁. Interestingly, the loss can theoretically fall below 1
when 𝐹≠𝐺(e.g., 𝐹= 1
𝑁+ 𝜖and 𝐺= 1
𝑁−𝜖), which we indeed observe during training. Despite this theoretical possibility,
the loss effectively guides the model toward the desired compression ratio in practice. In practice, as our architectural
design encourages the routing module to make confident decisions (i.e., boundary probabilities approaching 0 or 1), 𝐹
naturally co
```

## `hnet-v2:s3:c0002` p.10 [caption] digit_ratio=0.02
```
and
modifies the layer counts and widths slightly to match the H-Net models below.
• H-Net (space) further improves SpaceByte++ with our training improvements to the network (Section 2.3), in
particular, adding post-network norms, residual projections, and learning rate multipliers on the outer networks.
H-Net (space) differs from our full H-Net only through the chunking function.
10Here, we use token in the autoregressive generation sense, referring to one time step, not in the literal BPE token sense.
11This was called the "Transformer++" in Gu and Dao (2024); since by now it is firmly established, we remove the "++".
12BLT is another architecture with external supervision using entropy instead of delimiters, but is unfortunately too complex to set up and control as a
baseline. We believ
```

## `hnet-v2:s3:c0003` p.10 [caption] digit_ratio=0.033
```
to set up and control as a
baseline. We believe that the delimiter-based method is highly competitive. See Appendix A.1.3.
Table 1: Architectures for main language models, all data-/FLOP-matched. E0, D0 , E1, D1 , M . T and M denote
a Transformer and a Mamba-2 layer, respectively. For hierarchical byte-level models, the Tokenizer column lists the
chunking mechanism. The numbers before DC indicate downsampling factor 𝑁in equation (10); for example, (3,3)-DC
denotes 𝑁0 = 𝑁1 = 3. The BPIC (Bytes-Per-Innermost-Chunk) measure shows that each chunk dynamically determined by
our 1-stage comprises similar number of bytes to the GPT-2 tokenizer, despite aiming for 𝑁0 = 6. All Transformer layers in
E or D networks, as well as LlamaByte, use Sliding Window Attention (SWA) with a window size of 1024.

```

## `hnet-v2:s3:c0004` p.10 [numeric_dense] digit_ratio=0.327
```
Sliding Window Attention (SWA) with a window size of 1024.
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
1024 , 2048
H-Net (space)
Spacelike
6.0
1.6B
M4 + T
```

## `hnet-v2:s3.1:c0004` p.12 [numeric_dense,caption] digit_ratio=0.152
```
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
SpaceByte
Ll
```

## `hnet-v2:s3.1:c0005` p.12 [caption] digit_ratio=0.017
```
H-Net (space)
H-Net (6-pool)
SpaceByte++
SpaceByte
LlamaByte (SWA)
LlamaByte (Global)
(BPE) Transformer
MambaByte
Figure 3: Validation Bits-per-byte (BPB) throughout training for different models at Large (760M, left) and XL (1.3B,
right) scales with matched computational and data budgets for training. All models but Transformer take raw byte inputs
(Transformer uses GPT-2 tokenizer). Vertical dotted lines indicate crossover points where H-Net begins to outperform
Transformer with predefined BPE tokenization. From the curves we can clearly see the following: (1) all hierarchical
models (i.e., SpaceByte++, H-Net variants) outperform the isotropic models (i.e., Transformer, MambaByte, LlamaByte); (2)
dynamic chunking is more powerful than BPE tokenizers; and (3) DC is more effective than oth
```

## `hnet-v2:s3.1:c0006` p.12 [caption] digit_ratio=0.101
```
BPE tokenizers; and (3) DC is more effective than other chunking strategies.
Furthermore, H-Net’s 2-stage variant consistently outperforms 1-stage across both scales, demonstrating the effectiveness
of deeper hierarchies. See Table 1 for architectural details.
Table 2: Zero-shot performance comparison across multiple benchmarks, all data-/FLOP-matched. Evaluation
results on seven downstream tasks at both Large (760M) and XL (1.3B) scales. GFLOPs/Byte is measured during evaluation
on FineWeb-Edu validation set. See Table 1 for architectural details.
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
LlamaB
```

## `hnet-v2:s3.1:c0007` p.12 [mostly_digits] digit_ratio=0.556
```
Large
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
40.0
53.6
H-Net (2-stage)
0.43
0.743
46.9
57.4
72.0
71.7
39.2
60.4
40.6
55.5
#FLOPs matched to GPT-3 XL
Transformer
Token
0.69
0.730
48.1
58.0
73.1
72.2
37.5
58.6
40.8
55.5
SpaceByte++
0.72
0.733
51.3
60.1
72.4
71.8
38
```

## `hnet-v2:s3.1:c0008` p.12 [numeric_dense,caption] digit_ratio=0.179
```
58.6
40.8
55.5
SpaceByte++
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
adversarial text inputs than tokenizer-based Transformer. H-N
```

## `hnet-v2:s3.1:c0009` p.12 [numeric_dense] digit_ratio=0.264
```
text inputs than tokenizer-based Transformer. H-Net (2-stage) shows significantly enhanced robustness in
textual perturbations, with the highest average accuracy across all noise types and highest robustness score. See Table 1
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
30
```

## `hnet-v2:s3.1:c0010` p.12 [numeric_dense] digit_ratio=0.266
```
(pool)
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
30.9
32.1
40.3
30.6
58.5
38.5
38.5
H-Net (space)
31.2
33.2
41.9
31.8
60.7
39.8
40.5
H-Net (1-stage)
Byte
30.9
32.7
39.2
31.2
58.4
38.6
39.5
H-Net (2-stage)
31.1
34.7
44.1
33.0
61.7
40.9
42.8
Robustness to Textual Perturbations.
Table 3 evaluates model robustness on HellaSwag with various textual pertur-
bations, following protocols from BLT (Pagnoni et al. 2024). Importantly, these are the same checkpoints trained on clean
FineWeb-Edu data used to evaluate Table 2), without any form of special data mix or augm
```

## `hnet-v2:s3.2:c0000` p.15 [caption] digit_ratio=0.11
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

## `hnet-v2:s3.2:c0001` p.15 [caption] digit_ratio=0.043
```
with Transformer after around 25B bytes. On code, both H-Net (2-stage) and H-Net (space) significantly outperform BPE
Transformer. Final post-decay results can be found in Table 4.
H-Net can operate on raw data without the need for handcrafted features (whether vocabulary or deliniation cues); it
therefore provides a natural architecture that can operate naturally on any language.
Experimental setup for Chinese and code.
On Chinese and code, we use 46B token subset from FineWeb-Edu-Chinese-
V2.1 (Yu, Dai, et al. 2025) and Github subset from Pile (Gao, Biderman, et al. 2020) to train three models at the 1.3B GPT-3
XL scale: H-Net (2-stage), H-Net (space), and Transformer. We maintain the same bytes per gradient step (256 batch size
with 8192 utf-8 encoded bytes per example) as the main text
```

## `hnet-v2:s3.2:c0005` p.15 [caption] digit_ratio=0.02
```
and two corresponding H-Net (1-stage) with Transformer and Mamba-2 as the main network. Each model
was trained on the HG38 dataset with a learning rate of 5 · 10−3 for modules at the base-pair resolution. For the H-Net
Table 4: Architecture details and model benchmarks for Chinese and code models. BPIC (defined in Table 2) denotes
the compression between the main network and outermost stage (bytes). Each H-Net used (3,3)-DC, targeting an inner
downsampling ratio of 9. However, the resulting BPIC was significantly different, indicating that code is much easier to
compress than Chinese. In terms of results, H-Net (2-stage) performs better than both H-Net (space) and BPE Transformer
on Chinese, which is reflected in the downstreams. On the other hand, H-Net (2-stage) achieves similar performa
```

## `hnet-v2:s3.2:c0006` p.15 [numeric_dense,caption] digit_ratio=0.16
```
On the other hand, H-Net (2-stage) achieves similar performance to
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
H-Net (space)
3.38
T19
0.7478
0.629
7.97
T40
0.3163
H-Net (2-stage)
5.81
T30
0.7032
0.663
7.23
T28
0.3161
Model / Architecture
Params.
Final ppl. ↓
Transformer
( T9 )
29M
2.769
Mamba-2
( M10 )
33M
2.757
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
the corresponding isotropi
```

## `hnet-v2:s3.2:c0007` p.15 [caption] digit_ratio=0.055
```
H-Net model outperforms
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
approximately 3.6× less data.
models, we used a downsampling ratio of 𝑁0 = 3. All models were trained with a 𝑑model of 512, which was used for all
isotropic modules of H-Net (including the main network).
Previous work has shown that SSMs show improved DNA modeling ability 
```

## `hnet-v2:s3.3:c0001` p.17 [numeric_dense,caption] digit_ratio=0.157
```
dynamics. Without this module, compression ratios fluctuate
25B
50B
75B
100B
125B
Total Training Bytes
0.80
0.85
0.90
0.95
1.00
1.05
Bits-per-byte (2-stage)
25B
50B
75B
100B
125B
Total Training Bytes
0.34
0.35
0.36
0.37
0.38
Compression Ratio L1/L0
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
1
```

## `hnet-v2:s3.3:c0002` p.17 [caption] digit_ratio=0.129
```
the similarity-based routing module (w/o cosine
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
Figure 8: Encoder-decoder architecture ablation using raw byte inputs. Validation BPB (left) and compression ratio
𝐿1/𝐿0 (right) for H-Net (1-stage) throughout training. We evaluate four encoder-decoder (E0 −D0) configurations: M4-M4
, M2T1-T1M2 and T1M2-M2T1, and T2-T2, where M denotes Mamba layers and T denotes Transformer layers.
severely throughout training, preventing the model from learning consistent chunking boundaries. This instability directly
manifests as sub
```

## `hnet-v2:s3.3:c0004` p.17 [caption] digit_ratio=0.133
```
of sequence mixing layers in H-Net’s encoders and decoders
substantially influences both compression efficiency and modeling capability. We systematically evaluate different ar-
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
```

## `hnet-v2:s3.3:c0005` p.17 [numeric_dense,caption] digit_ratio=0.156
```
M4-M4 , M2T1-T1M2 and
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
0.975
1.000
Bits-per-byte
T3-T3
T2M2-M2T2
M2T2-T2M2
T1M4-M4T1
M4T1-T1M4
M6-M6
Figure 10: Encoder-decoder architecture ablation us-
ing BPE-tokenized inputs. Assuming that GPT-2 tok-
enizer serves as the outermost encoder-decoder (i.e., E0-D0),
we evaluate six E1-D1 combinations: M6-M6, M4T1-T1M4,
T1M4-M4T1, M2T2-T2M2, T2M2-M2T2, and T3-T3.
layer and T denotes a Transformer layer. These combinations are chosen by keeping the symmetry and replacing each
Transformer layer with two Mamba-2 layers, as they contain equivalent parameter counts — 12𝐷2 for Transformer (4𝐷2
for the attention mechanism and 8𝐷2 fo
```

## `hnet-v2:s3.3:c0007` p.17 [caption] digit_ratio=0.017
```
efficiency in the pure Mamba configuration
(M4-M4). These findings align with recent research demonstrating SSMs’ advantages over Transformers for fine-grained
sequence modeling (Goel et al. 2022; Schiff et al. 2024), as corroborated by MambaByte’s superior performance over
LlamaByte in Figure 3.
A natural question arises: does the importance of Mamba layers (i) stem specifically from processing fine-grained byte
inputs, or (ii) because they are better for compressing information into the next stage, even at coarser input
resolutions? To investigate these hypotheses, we train a 1-stage H-Net on top of BPE-tokenized inputs processed by the
GPT-2 tokenizer. We then evaluate six different encoder-decoder combinations.
• If hypothesis (i) holds, then we would expect different combinations of M
```

## `hnet-v2:s3.3:c0009` p.17 [caption] digit_ratio=0.065
```
caches for all positions, SSMs
are designed to compress information into fixed-size states. This compression-oriented architecture aligns naturally with
our chunking mechanism, which requires aggregating multiple input vectors into consolidated representations. The
inherent compression capability of Mamba layers makes them particularly well-suited for the encoder and decoder roles in
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
the stable phase of training, fo
```

## `hnet-v2:s3.3:c0010` p.17 [caption] digit_ratio=0.069
```
Bits-per-byte during
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
1.00
1.05
Bits-per-byte
LlamaByte (200M)
LlamaByte MoE (860M)
H-Net (1-stage, 680M)
H-Net (2-stage, 870M)
Figure 12: Comparison to Mixtures-of-Experts. Bits-
per-byte comparison of H-Net (both 1-stage and 2-stage) to
LlamaByte-MoE, which is a FLOPs-matched MoE model that
uses a similar number of parameters as H-Net (2-stage). Both
H-Nets perform much better than LlamaByte-MoE,
```

## `hnet-v2:s3.3:c0013` p.17 [caption] digit_ratio=0.008
```
count as ours (Figure 12).
While sparsity does improve LlamaByte performance, it is still far worse than either FLOPs-matched H-Net (1-stage) or
H-Net (2-stage), even with similar parameter count. We interpret this result as: H-Net not only achieves sparsity, but does
so in a more semantically meaningful manner, which allows for better scaling than even generic sparse methods.
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
C
```

## `hnet-v2:s5:c0038` p.23 [caption] digit_ratio=0.009
```
methods have emerged that avoid the reliance on predefined vocabularies.
• In Appendix A.1, we discuss the most directly related prior work on autoregressive sequence models, extending the
overview from Section 1.
• In Appendix A.2, we discuss non-autoregressive models. We note that essentially all autoregressive architectures
can be turned into non-autoregressive architectures (including our proposed H-Net), and vice versa, which provide
possible extensions of H-Net in future work. However, we provide this delineation because it marks an important
difference in motivation that influences design considerations and downstream evaluations.
• Appendix A.3 mentions other works in non-language modalities related to tokenization.
We summarize our discussion on tokenizer-free architectures in Tab
```

## `hnet-v2:s5:c0039` p.23 [caption] digit_ratio=0.011
```
our discussion on tokenizer-free architectures in Table 6.
A.1
Autoregressive Tokenizer-free Architectures
As outlined in Section 1, prior work on autoregressive tokenizers for architectures can be divided into four categories:
1. Non-hierarchical isotropic architectures.
2. Hierarchical architectures with static chunking strategies, where chunk boundaries are content-agnostic (usually
some variant of fixed-width pooling).
3. Hierarchical architectures with external chunking strategeies, where chunk boundaries are provided by an external
function or module.
4. Hierarchical architectures with dynamic chunking strategies, where chunk boundaries are content-dependent and
learned end-to-end.
A.1.1
Isotropic Architectures
The most direct approach to modeling language with tokenizers is to simpl
```

## `hnet-v2:s5:c0062` p.23 [equation] digit_ratio=0.065
```
pass consumes twice the FLOPs of the forward pass.
Learning Rate Modulation
As discussed in Section 2.3, we employ modulated learning rates for each stage by multiplying a scalar 𝜆𝑠to the base
learning rate. Empirically, we find that a reasonable set of multipliers (e.g., 𝜆0 = 2.0, 𝜆1 = 1.5, 𝜆2 = 1.0) works well in general.
To provide a more systematic experimental results across different architectural configurations, we follow previous works
and set learning rates to be proportionally to the (1) square root of batch size (Malladi et al. 2022; Merrill et al. 2025), and
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
Cross A
```

## `hnet-v2:s5:c0063` p.23 [caption] digit_ratio=0.054
```
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
where 𝑁GPT is the average number of bytes per token of training dataset, which is 4.6 for the GPT-2 tokenizer on
FineWeb-Edu.
We note that such principles for optimizing signal propagation as neural network hyperparameters change is an active
area of research, and
```

## `hnet-v2:s5:c0066` p.23 [caption] digit_ratio=0.118
```
as pooling or cross-attention.
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
results are still better than isotropic models (Table 5).
Transformers in the encoder network do not appear to
be helpful for text (Figure 8), suggesting that this finding
may be modality-specific.
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
stable phase of training. The pure Mamba-2 model
```

## `hnet-v2:s5:c0068` p.23 [caption] digit_ratio=0.02
```
of XWinograd, a Chinese language-understanding task.
For model architecture, we primarily matched the settings from the GPT-3 XL, including 𝑑model and encoder/decoder
architecture for H-Net models. However, we adjusted the number of layers in the main network of each model to account
for slightly different compression ratios. Specifically, the Chinese-language models used a slightly higher total training
flops target than the original language models, while the code models used a lower flops target. Full architecture details
and results are also in Table 4.
E.3
DNA Architecture Ablations
H-Net (1-stage) with an M3T1 encoder achieves 3.6× the data efficiency of an isotropic architecture (Figure 6). As
mentioned in the caption of Table 5, we found that an M3T1 encoder outperformed a pure Mam
```

## `hnet-v2:s5:c0070` p.23 [caption] digit_ratio=0.021
```
the tokenizer, embedding module, and LM head in a traditional
BPE-based language model; together, these modules interconvert between raw text and an embedding space that the main
model backbone can process. Given this similarity, we investigated whether it would be possible to convert a BPE-tokenized
model directly into a byte level H-Net. To do this, we trained a 1-stage H-Net with frozen main network initialized from
the backbone of Llama 3.2 3B (base). Our H-Net uses 4 Mamba-2 layers without MLPs for both the encoder and decoder
with a hidden dimension of 1536. Because the Llama model has a hidden dimension of 3072, we add MLP adapters with
Ground Truth
Boundaries
BCE Loss
Ground Truth
Embeddings
Copy + Shift
MSE Loss
Figure 15: Auxiliary loss strategy for training the encoder of a H-Ne
```

## `hnet-v2:s5:c0071` p.23 [caption] digit_ratio=0.007
```
loss strategy for training the encoder of a H-Net with pretrained main stage. In order to mimic
the behavior of the tokenizer + embedding layer of a pretrained language model, we add supervision to both the routing
module boundary probabilities and to the hidden states that we pass through to the main network. These losses encourage
the encoder to tokenize once at the start of every token, while also passing the correct embedding into the main network
near the start of the token, thus making maximal use of the next-token prediction ability.
Table 8: Distilling Llama 3.2 3B to a byte level model. Average acc indicates average of the benchmarks measured in
Table 2. H-Net loses performance across the board compared to the teacher, which is expected because we cannot quite
replicate the exact 
```
