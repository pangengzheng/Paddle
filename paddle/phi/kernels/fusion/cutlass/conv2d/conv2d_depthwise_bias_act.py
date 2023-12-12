# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys

sys.path.append("../")
import enum

from conv2d_common import (
    CommonConvFunction,
    CommonCutlassConv2dDepthwiseKernelDeclare,
    CommonCutlassConvKernelExecute,
    CommonTail,
)
from util import SubstituteTemplate

# this is a file's header part

cdba_header = '''
// Generated by conv2d_depthwise_bias_act.py - Do not edit.

#include <mutex>
#include "paddle/phi/kernels/fusion/cutlass/conv2d/conv2d_util.h"
#include <stdio.h>
#include <algorithm>
#include "cutlass/cutlass.h"
#include "cutlass/gemm/device/gemm.h"
#include "cutlass/conv/kernel/default_depthwise_fprop.h"
#include "cutlass/epilogue/thread/linear_combination_silu.h"
#include "cutlass/conv/device/direct_convolution.h"

#include "cutlass/conv/device/implicit_gemm_convolution.h"
#include "cutlass/conv/kernel/default_conv2d_fprop.h"
namespace phi {
namespace fusion {
namespace cutlass_internal {
'''

# This is a cutlass kernel, will be many these like kernels

dict_for_declare_part = {
    "conv_kind_name": "DefaultDepthwiseDirect2dConvFprop",
    "epi_part": "${epi_func}< ${element_c}, ${epilogue_vector_length}, ${element_accum}, ${element_epilogue}>",
    "swizzling_functor": '''cutlass::conv::threadblock::DepthwiseDirect2dConvIdentityThreadblockSwizzle<${swizzling_shape}>''',
}

cba_kernel_no_alpha = (
    SubstituteTemplate(
        CommonCutlassConv2dDepthwiseKernelDeclare, dict_for_declare_part
    )
    + '''
size_t filter_size = oc * kh * kw * kc * sizeof(half);
phi::Allocator::AllocationPtr filter_gpu_ptrs_data =
    phi::memory_utils::Alloc(
        params.ctx->GetPlace(),
        filter_size,
        phi::Stream(reinterpret_cast<phi::StreamId>(params.ctx->stream())));
void *filter_workspace = filter_gpu_ptrs_data->ptr();

      typename ImplicitGemm::Arguments arguments{
          problem_size,
          {(cutlass::half_t *)input, {ic, ic * iw, ic * iw * ih}},
          {(cutlass::half_t *)weight, {kc, kc * kw, kc * kw * kh}},
          {(cutlass::half_t *)bias, {0, 0, 0}},
          {(cutlass::half_t *)output, {oc, oc * ow, oc * ow * oh}},
          {1.f, 1.f},
           {(cutlass::half_t *)filter_workspace, {kc, kc * kw, kc * kw * kh}},
           };
'''
    + CommonCutlassConvKernelExecute
)


class CbaAct(enum.Enum):
    Identity = 1
    Relu = 2
    Sigmoid = 3
    Silu = 4


# Some global variables used, now we only support these activations.
SupportedAct = [CbaAct.Identity, CbaAct.Relu, CbaAct.Sigmoid, CbaAct.Silu]

ActTag = {
    SupportedAct[0]: 'cutlass::epilogue::thread::LinearCombination',
    SupportedAct[1]: 'cutlass::epilogue::thread::LinearCombinationRelu',
    SupportedAct[2]: 'cutlass::epilogue::thread::LinearCombinationSigmoid',
    SupportedAct[3]: 'cutlass::epilogue::thread::LinearCombinationSilu',
}

UnderScoreName = {
    SupportedAct[0]: "conv2d_depthwise_bias",
    SupportedAct[1]: "conv2d_depthwise_bias_relu",
    SupportedAct[2]: "conv2d_depthwise_bias_sigmoid",
    SupportedAct[3]: "conv2d_depthwise_bias_silu",
}

CamelName = {
    SupportedAct[0]: "Conv2dDepthwiseBias",
    SupportedAct[1]: "Conv2dDepthwiseBiasRelu",
    SupportedAct[2]: "Conv2dDepthwiseBiasSigmoid",
    SupportedAct[3]: "Conv2dDepthwiseBiasSilu",
}


def intlist2str(input):
    return_str = ""
    for i in range(len(input)):
        return_str += str(input[i])
        if i != len(input) - 1:
            return_str += ","
    return return_str


# Generate simt conv2d_depthwsie code.


def generate_conv2d_depthwise():
    kernel_dict = {
        "element_a": "cutlass::half_t",
        "layout_a": "cutlass::layout::TensorNHWC",
        "element_b": "cutlass::half_t",
        "layout_b": "cutlass::layout::TensorNHWC",
        "element_c": "cutlass::half_t",
        "layout_c": "cutlass::layout::TensorNHWC",
        "element_accum": "cutlass::half_t",
        "opcode_class": "cutlass::arch::OpClassSimt",
        "arch": "cutlass::arch::Sm70",
        "Ishape": "1,1,1",
        "stages": "2",
        # alpha is always float!
        "element_epilogue": "float",
        "math_operator": "cutlass::arch::OpMultiplyAdd",
        "iterator_algorithm": "cutlass::conv::IteratorAlgorithm::kFixedStrideDilation",
        "stride_support": "cutlass::conv::StrideSupport::kStrided",
        "dilation_shape": "1, 1",
    }

    # this should divided by oc
    kernel_dict["epilogue_vector_length"] = "4"

    all_code = ""
    for epi_func in SupportedAct:
        op_dict = {}
        # Because conv2d_depthwise is not related to the sm version,
        # so "func_name" are directly called by phi, we camel its name.
        op_dict["func_name"] = CamelName[epi_func]
        # enum_op_name is consistent with OpType in conv2d_util.h
        op_dict["enum_op_name"] = UnderScoreName[epi_func].upper()
        # For a function, we record all its kernels into a std::vector in C++ code
        all_kernel_names = ""
        kernel_dict["epi_func"] = ActTag[epi_func]
        suffix = 0

        filter_shapes = [[3, 3], [5, 5]]
        stride_shapes = ["1,1", "2,2"]

        # set [1,2,4,8] will generate too many kernels!
        # Now only set [8]
        for vec_length in ["8"]:
            kernel_dict["epilogue_vector_length"] = vec_length
            for filter_shape in filter_shapes:
                for stride_shape in stride_shapes:
                    tiles = [
                        # [out_h, out_w, groups_per_cta, warp_m]
                        # out_h, out_w : per cta would process
                        # groups_per_cta: per cta would process
                        # warp_m: per warp would process
                        [8, 8, 16, 16],
                        # [8, 16, 16, 16],
                        # [16, 8, 16, 16],
                        [8, 8, 32, 16],
                        # [8, 16, 32, 16],
                        # [16, 8, 32, 16],
                    ]
                    filter_size = filter_shape[0] * filter_shape[1]
                    for tile in tiles:
                        # per cta would process [1,out_h,out_w,groups_per_cta] output
                        kernel_dict["T_output_shape"] = intlist2str(
                            [1, tile[0], tile[1], tile[2]]
                        )
                        # per cta would process from the view of gemm
                        kernel_dict["Tshape"] = intlist2str(
                            [tile[0] * tile[1], tile[2], filter_size]
                        )
                        kernel_dict["Wshape"] = intlist2str(
                            [tile[3], tile[2], filter_size]
                        )
                        kernel_dict["swizzling_shape"] = intlist2str(
                            [1, 1, tile[0], tile[1]]
                        )

                        kernel_dict["split_k_slices"] = "(oh * ow + 63) / 64"

                        kernel_dict["filter_shape"] = intlist2str(filter_shape)
                        kernel_dict["strided_shape"] = stride_shape
                        kernel_dict["kernel_func_name"] = (
                            UnderScoreName[epi_func].lower() + "_" + str(suffix)
                        )
                        suffix += 1
                        all_code += SubstituteTemplate(
                            cba_kernel_no_alpha, kernel_dict
                        )
                        all_kernel_names += (
                            kernel_dict["kernel_func_name"] + ", \n"
                        )
        # generate op code
        op_dict["all_kernel_func_name"] = all_kernel_names
        all_code += SubstituteTemplate(CommonConvFunction, op_dict)
    return all_code


if __name__ == "__main__":
    all_code = cdba_header
    all_code += generate_conv2d_depthwise()
    all_code += CommonTail
    with open("generated_tmp/conv2d_depthwise_bias_act.cu", "w") as f:
        f.write(all_code)
        f.close()
