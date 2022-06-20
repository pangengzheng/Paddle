/* Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. */

#pragma once
#include <vector>
#include "paddle/fluid/framework/fleet/heter_ps/feature_value.h"
#include "paddle/fluid/framework/fleet/heter_ps/heter_resource.h"
#include "paddle/fluid/framework/fleet/heter_ps/optimizer_conf.h"

#ifdef PADDLE_WITH_HETERPS

namespace paddle {
namespace framework {

class HeterPsBase {
 public:
  HeterPsBase() {}
  HeterPsBase(size_t capacity, std::shared_ptr<HeterPsResource> resource) {}
  virtual ~HeterPsBase() {}
  HeterPsBase(const HeterPsBase&) = delete;
  HeterPsBase& operator=(const HeterPsBase&) = delete;

#if defined(PADDLE_WITH_XPU_KP)
  virtual void pull_sparse(int num, FidKey* d_keys, FeatureValue* d_vals,
                           size_t len) = 0;
  virtual void build_ps(int num, FidKey* h_keys, FeatureValue* h_vals,
                        size_t len, size_t chunk_size, int stream_num) = 0;
#else
  virtual void pull_sparse(int num, FeatureKey* d_keys, FeatureValue* d_vals,
                           size_t len) = 0;
  virtual void build_ps(int num, FeatureKey* h_keys, FeatureValue* h_vals,
                        size_t len, size_t chunk_size, int stream_num) = 0;
#endif

  virtual int get_index_by_devid(int devid) = 0;
#if defined(PADDLE_WITH_CUDA)
  virtual void set_nccl_comm_and_size(
      const std::vector<ncclComm_t>& inner_comms,
      const std::vector<ncclComm_t>& inter_comms, int comm_size) = 0;
#endif
  virtual void end_pass() = 0;
  virtual void show_one_table(int gpu_num) = 0;

#if defined(PADDLE_WITH_XPU_KP)
  virtual void push_sparse(int num, FidKey* d_keys,
                           FeaturePushValue* d_grads, size_t len) = 0;
#else
  virtual void push_sparse(int num, FeatureKey* d_keys,
                           FeaturePushValue* d_grads, size_t len) = 0;
#endif

  virtual void set_sparse_sgd(const OptimizerConfig& optimizer_config) = 0;
  virtual void set_embedx_sgd(const OptimizerConfig& optimizer_config) = 0;

  static HeterPsBase* get_instance(size_t capacity,
                                   std::shared_ptr<HeterPsResource> resource);
};

}  // end namespace framework
}  // end namespace paddle
#endif
